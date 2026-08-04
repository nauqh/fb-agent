"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

/**
 * The Cart: the set of Source Items ticked for the next generation run.
 *
 * Client state, a list of ids, not persisted — there is no cart table, because
 * nothing about a Cart needs to survive that is not already a row. It lives in
 * the root layout so it survives navigation from Sources to Generate, which is
 * the only journey it has to make.
 */

interface CartValue {
  ids: number[];
  count: number;
  has: (id: number) => boolean;
  add: (id: number) => void;
  remove: (id: number) => void;
  clear: () => void;
}

const CartContext = createContext<CartValue | null>(null);

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [ids, setIds] = useState<number[]>([]);

  const add = useCallback((id: number) => {
    setIds((current) => (current.includes(id) ? current : [...current, id]));
  }, []);

  const remove = useCallback((id: number) => {
    setIds((current) => current.filter((candidate) => candidate !== id));
  }, []);

  const clear = useCallback(() => setIds([]), []);

  const value = useMemo<CartValue>(
    () => ({
      ids,
      count: ids.length,
      has: (id) => ids.includes(id),
      add,
      remove,
      clear,
    }),
    [ids, add, remove, clear],
  );

  return <CartContext value={value}>{children}</CartContext>;
}

export function useCart(): CartValue {
  const value = useContext(CartContext);
  if (!value) throw new Error("useCart must be used inside CartProvider");
  return value;
}
