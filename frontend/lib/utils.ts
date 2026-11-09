import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const money = (n: number) => "$" + Math.round(n).toLocaleString("en-US");

export const moneyCents = (n: number) =>
  "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const moneyCompact = (n: number) => (Math.abs(n) >= 1000 ? `$${(n / 1000).toFixed(1)}k` : money(n));

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-11" -> "Nov" */
export function shortMonth(ym: string) {
  const m = Number(ym.split("-")[1]);
  return MONTHS[m - 1] ?? ym;
}

/** "2026-11" -> "Nov 2026" */
export function monthLabel(ym: string) {
  const [y] = ym.split("-");
  return `${shortMonth(ym)} ${y}`;
}

/**
 * Categorical palette shared by the 3D scene, donut and legends.
 * Mid-tone hues chosen to stay legible on both light and dark surfaces.
 */
export const SERVICE_COLORS = ["#3E63DD", "#1F9D84", "#D4903A", "#7C66DC", "#3A95B4", "#C9677B"];
