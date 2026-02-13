interface BadgeProps {
  variant?: 'gold' | 'green' | 'red';
  children: React.ReactNode;
}

export default function Badge({ variant = 'gold', children }: BadgeProps) {
  return <span className={`badge badge-${variant}`}>{children}</span>;
}
