"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

import type { LiveSourceItem } from "@/lib/api/sources";

/**
 * The Cart: the Source Items ticked for the next generation run.
 *
 * It holds the **items**, not row ids, and that is the whole point. Nothing is
 * written until `POST /generate` uses them, so ticking is instant and offline,
 * unticking leaves nothing behind, and there is no orphan row to clean up. It
 * used to hold ids, which meant a tick was a round trip that created a row and
 * an untick silently abandoned it — see docs/plan.md, "Ticking stops writing".
 *
 * Client state, not persisted: there is no cart table, because nothing about a
 * Cart needs to survive that is not already a row. It lives in the root layout
 * so it survives navigation from Sources to Generate, the only journey it makes.
 */

/** Identity of a Source Item before it is a row. Matches the server's dedup key. */
export function sourceKey(item: Pick<LiveSourceItem, "kind" | "external_id">): string {
  return `${item.kind}:${item.external_id}`;
}

interface CartValue {
  items: LiveSourceItem[];
  count: number;
  has: (item: Pick<LiveSourceItem, "kind" | "external_id">) => boolean;
  add: (item: LiveSourceItem) => void;
  remove: (item: Pick<LiveSourceItem, "kind" | "external_id">) => void;
  toggle: (item: LiveSourceItem) => void;
  clear: () => void;
}

const CartContext = createContext<CartValue | null>(null);

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<LiveSourceItem[]>([]);

  const add = useCallback((item: LiveSourceItem) => {
    setItems((current) =>
      current.some((candidate) => sourceKey(candidate) === sourceKey(item))
        ? current
        : [...current, item],
    );
  }, []);

  const remove = useCallback((item: Pick<LiveSourceItem, "kind" | "external_id">) => {
    setItems((current) =>
      current.filter((candidate) => sourceKey(candidate) !== sourceKey(item)),
    );
  }, []);

  const clear = useCallback(() => setItems([]), []);

  const value = useMemo<CartValue>(() => {
    const keys = new Set(items.map(sourceKey));
    return {
      items,
      count: items.length,
      has: (item) => keys.has(sourceKey(item)),
      add,
      remove,
      toggle: (item) => (keys.has(sourceKey(item)) ? remove(item) : add(item)),
      clear,
    };
  }, [items, add, remove, clear]);

  return <CartContext value={value}>{children}</CartContext>;
}

export function useCart(): CartValue {
  const value = useContext(CartContext);
  if (!value) throw new Error("useCart must be used inside CartProvider");
  return value;
}
