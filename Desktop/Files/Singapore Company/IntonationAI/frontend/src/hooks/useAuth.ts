"use client";

import { useState, useEffect } from "react";
import { type User } from "firebase/auth";
import { onAuthChange, signOut } from "@/lib/firebase";

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const unsub = onAuthChange((u) => {
      setUser(u);
      setLoading(false);
    });
    return unsub;
  }, []);

  return { user, loading, signOut };
}
