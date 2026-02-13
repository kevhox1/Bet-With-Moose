'use client';
import { ReactNode } from 'react';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

export default function Modal({ open, onClose, children }: ModalProps) {
  if (!open) return null;
  return (
    <div className="age-gate-overlay" onClick={onClose}>
      <div className="card" style={{ maxWidth: 480, minWidth: 320 }} onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}
