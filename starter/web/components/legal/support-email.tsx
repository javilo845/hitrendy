"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";

const DEMO_SUPPORT_EMAIL = "support@hitrendy.local";

export function SupportEmail() {
  const [email, setEmail] = useState(DEMO_SUPPORT_EMAIL);

  useEffect(() => {
    let active = true;
    void api.operations
      .policies()
      .then((policies) => {
        if (active && policies.support.email.includes("@")) {
          setEmail(policies.support.email);
        }
      })
      .catch(() => {
        // The demo fallback keeps the legal pages readable if the API is down.
      });
    return () => {
      active = false;
    };
  }, []);

  return <a href={`mailto:${email}`}>{email}</a>;
}
