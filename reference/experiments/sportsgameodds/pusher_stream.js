/**
 * SportsGameOdds Pusher Streaming Client
 * ======================================
 * Real-time odds updates via official Pusher JS client.
 *
 * Usage:
 *   node pusher_stream.js
 *
 * This connects to SportsGameOdds WebSocket and receives
 * real-time notifications when NBA event odds change.
 */

const fetch = require("node-fetch");
const Pusher = require("pusher-js");

// Configuration
const API_KEY = "7546525eada0352b926e60dbc6c42cb0";
const API_BASE_URL = "https://api.sportsgameodds.com/v2";
const STREAM_FEED = "events:upcoming";
const LEAGUE_ID = "NBA";

// State
let EVENTS = new Map();
let pusher = null;
let channel = null;
let updatesReceived = 0;
let connectionState = "disconnected";

/**
 * Make API request with retry logic
 */
const apiRequest = async (endpoint, params = {}) => {
  const url = new URL(`${API_BASE_URL}${endpoint}`);
  Object.keys(params).forEach(k => url.searchParams.append(k, params[k]));

  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const response = await fetch(url.toString(), {
        headers: { "x-api-key": API_KEY }
      });

      if (response.status === 503) {
        console.log(`   API returned 503, retry ${attempt}/3...`);
        await new Promise(r => setTimeout(r, 2000 * attempt));
        continue;
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      if (attempt === 3) throw error;
      console.log(`   Request failed, retry ${attempt}/3...`);
      await new Promise(r => setTimeout(r, 2000 * attempt));
    }
  }
};

/**
 * Format event title for display
 */
const getEventTitle = (event) => {
  const away = event.teams?.away?.names?.medium || event.teams?.away?.names?.short || "Away";
  const home = event.teams?.home?.names?.medium || event.teams?.home?.names?.short || "Home";
  return `${away} @ ${home}`;
};

/**
 * Compare odds and find what changed
 */
const compareOdds = (prevEvent, newEvent) => {
  const changes = [];
  const prevOdds = prevEvent?.odds || {};
  const newOdds = newEvent?.odds || {};

  // Player prop stat types we care about
  const playerPropStats = [
    'points', 'rebounds', 'assists', 'threePointersMade', 'blocks', 'steals',
    'doubleDouble', 'tripleDouble', 'firstBasket',
    'points+rebounds', 'points+assists', 'points+rebounds+assists'
  ];

  for (const [oddId, newOddData] of Object.entries(newOdds)) {
    // Parse oddId: statID-playerID-period-betType-side
    const parts = oddId.split('-');
    if (parts.length < 5) continue;

    const [statId, playerId, period, betType, side] = parts;

    // Skip non-player props
    if (['all', 'home', 'away'].includes(playerId)) continue;
    if (period !== 'game') continue;
    if (!playerPropStats.includes(statId)) continue;

    const prevOddData = prevOdds[oddId];
    const newByBook = newOddData.byBookmaker || {};
    const prevByBook = prevOddData?.byBookmaker || {};

    // Check each book for changes
    for (const [bookId, bookData] of Object.entries(newByBook)) {
      const prevBookData = prevByBook[bookId];
      const newPrice = bookData.price;
      const prevPrice = prevBookData?.price;

      // New book or price changed
      if (prevPrice === undefined || newPrice !== prevPrice) {
        const playerName = newEvent.players?.[playerId]?.name || playerId.replace(/_/g, ' ');
        const line = newOddData.fairOverUnder || newOddData.bookOverUnder || '';

        changes.push({
          player: playerName,
          stat: statId,
          line: line,
          side: side,
          book: bookId,
          oldPrice: prevPrice,
          newPrice: newPrice
        });
      }
    }
  }

  return changes;
};

/**
 * Format price for display
 */
const formatPrice = (price) => {
  if (price === undefined) return 'NEW';
  return price > 0 ? `+${price}` : `${price}`;
};

/**
 * Handle real-time odds update
 */
const handleOddsUpdate = async (changedEvents) => {
  updatesReceived++;
  const timestamp = new Date().toISOString().substr(11, 8);

  console.log(`\n${"=".repeat(60)}`);
  console.log(`[UPDATE #${updatesReceived}] ${changedEvents.length} event(s) changed @ ${timestamp}`);

  // Get eventIDs
  const eventIDs = changedEvents.map(e => e.eventID).join(",");
  if (!eventIDs) return;

  // Fetch full event data
  const startTime = Date.now();
  try {
    const data = await apiRequest("/events", { eventIDs });
    const fetchTime = Date.now() - startTime;

    console.log(`   Fetched in ${fetchTime}ms`);

    // Compare and show changes
    data.data.forEach((newEvent) => {
      const prevEvent = EVENTS.get(newEvent.eventID);
      console.log(`\n   ${getEventTitle(newEvent)}`);

      // Find what changed in player props
      const changes = compareOdds(prevEvent, newEvent);

      if (changes.length === 0) {
        console.log(`   (No player prop changes - likely game lines)`);
      } else {
        // Group by player
        const byPlayer = {};
        changes.forEach(c => {
          if (!byPlayer[c.player]) byPlayer[c.player] = [];
          byPlayer[c.player].push(c);
        });

        // Show up to 10 changes
        let shown = 0;
        for (const [player, playerChanges] of Object.entries(byPlayer)) {
          if (shown >= 10) {
            console.log(`   ... and ${changes.length - shown} more changes`);
            break;
          }
          for (const c of playerChanges) {
            if (shown >= 10) break;
            const arrow = c.oldPrice === undefined ? '(NEW)' :
              `${formatPrice(c.oldPrice)} -> ${formatPrice(c.newPrice)}`;
            console.log(`   ${player} ${c.stat} ${c.side} ${c.line}: ${c.book} ${arrow}`);
            shown++;
          }
        }
      }

      // Update stored event
      EVENTS.set(newEvent.eventID, newEvent);
    });

  } catch (error) {
    console.error(`   Error fetching events: ${error.message}`);
  }
};

/**
 * Main connection function
 */
const connect = async () => {
  console.log("=".repeat(60));
  console.log("SportsGameOdds Pusher Streaming Client");
  console.log("=".repeat(60));
  console.log(`\n[INIT] Feed: ${STREAM_FEED}, League: ${LEAGUE_ID}`);

  try {
    // Step 1: Get stream configuration
    console.log("[INIT] Fetching stream configuration...");

    const streamData = await apiRequest("/stream/events", {
      feed: STREAM_FEED,
      leagueID: LEAGUE_ID
    });

    const { data: initialEvents, pusherKey, pusherOptions, channel: channelName } = streamData;

    console.log(`[INIT] Pusher Key: ${pusherKey}`);
    console.log(`[INIT] Channel: ${channelName}`);
    console.log(`[INIT] Cluster: ${pusherOptions.cluster}`);
    console.log(`[INIT] Initial events: ${initialEvents.length}`);

    // Seed initial data
    initialEvents.forEach((event) => {
      EVENTS.set(event.eventID, event);
      console.log(`   - ${getEventTitle(event)}`);
    });

    // Step 2: Connect to Pusher
    console.log("\n[CONNECT] Initializing Pusher connection...");

    // Enable logging for debugging
    Pusher.logToConsole = false;  // Set to true for verbose logging

    pusher = new Pusher(pusherKey, pusherOptions);

    // Connection state handlers
    pusher.connection.bind("state_change", (states) => {
      connectionState = states.current;
      console.log(`[STATE] ${states.previous} -> ${states.current}`);
    });

    pusher.connection.bind("connected", () => {
      console.log("[CONNECTED] WebSocket connection established");
    });

    pusher.connection.bind("error", (error) => {
      console.error(`[ERROR] Connection error: ${JSON.stringify(error)}`);
    });

    // Step 3: Subscribe to channel
    console.log(`[SUBSCRIBE] Subscribing to ${channelName}...`);

    channel = pusher.subscribe(channelName);

    channel.bind("pusher:subscription_succeeded", () => {
      console.log(`[SUBSCRIBED] Successfully subscribed to ${channelName}`);
      console.log("\n[STREAM] Waiting for odds updates... (Ctrl+C to stop)\n");
    });

    channel.bind("pusher:subscription_error", (error) => {
      console.error(`[ERROR] Subscription failed: ${JSON.stringify(error)}`);
    });

    // Step 4: Handle data events (odds updates)
    channel.bind("data", handleOddsUpdate);

    // Heartbeat
    setInterval(() => {
      console.log(`[HEARTBEAT] State: ${connectionState}, Updates: ${updatesReceived}, Events: ${EVENTS.size}`);
    }, 30000);

  } catch (error) {
    console.error(`[ERROR] Failed to connect: ${error.message}`);
    process.exit(1);
  }
};

/**
 * Graceful shutdown
 */
const disconnect = () => {
  console.log("\n[STOP] Shutting down...");

  if (channel) {
    pusher.unsubscribe(channel.name);
  }
  if (pusher) {
    pusher.disconnect();
  }

  console.log(`[STATS] Total updates received: ${updatesReceived}`);
  console.log(`[STATS] Events tracked: ${EVENTS.size}`);
  process.exit(0);
};

// Handle Ctrl+C
process.on("SIGINT", disconnect);
process.on("SIGTERM", disconnect);

// Start
console.log("Starting SportsGameOdds Pusher streaming client...\n");
connect();
