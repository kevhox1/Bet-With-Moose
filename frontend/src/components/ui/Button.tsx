import { ButtonHTMLAttributes } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'gold' | 'outline';
  size?: 'sm' | 'md' | 'lg';
}

export default function Button({ variant = 'primary', size = 'md', className = '', children, ...props }: ButtonProps) {
  const cls = `btn btn-${variant} ${size !== 'md' ? `btn-${size}` : ''} ${className}`.trim();
  return <button className={cls} {...props}>{children}</button>;
}
