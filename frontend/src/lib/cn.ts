// 经典 className 合并（shadcn 风格）。
// 暂不引 tailwind-merge，等真有冲突再加。
import { clsx, type ClassValue } from 'clsx';

export function cn(...inputs: ClassValue[]): string {
  return clsx(...inputs);
}
