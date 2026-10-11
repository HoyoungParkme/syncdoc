/**
 * 물건 화면 — FX-UI-001#UI-3
 */
import base from "../api";
import { api as client } from "../api/client";
import * as C from "../components/Card";
import React from "react";

export default function ThingPage() {
  const load = async () => {
    await client.get(base());
  };
  React.useEffect(() => {
    load();
  }, []);
  return (
    <div>
      <C.Card title="x" />
      <Inner />
    </div>
  );
}

function Inner() {
  return <span>{client.post("/x", 1) && "y"}</span>;
}
