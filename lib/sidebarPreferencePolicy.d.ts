export const SIDEBAR_PREFERENCE_KEY: string;

type SidebarStorage = Pick<Storage, 'getItem' | 'setItem'>;

export function readSidebarCollapsed(storage?: SidebarStorage | null): boolean;
export function writeSidebarCollapsed(
  storage: SidebarStorage | null | undefined,
  collapsed: boolean
): void;
