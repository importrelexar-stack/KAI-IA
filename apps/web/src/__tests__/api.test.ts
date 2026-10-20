import { describe, expect, it } from "vitest";
import { parseSseChunk } from "../lib/api";

describe("parseSseChunk", () => {
  it("parsea eventos completos y conserva el resto", () => {
    const buf =
      'event: meta\ndata: {"type":"meta","conversation_id":"c1"}\n\n' +
      'event: delta\ndata: {"type":"delta","text":"Ho"}\n\n' +
      'event: delta\ndata: {"type":"del';
    const { events, rest } = parseSseChunk(buf);
    expect(events.map((e) => e.type)).toEqual(["meta", "delta"]);
    expect(rest).toBe('event: delta\ndata: {"type":"del');
  });

  it("ignora datos corruptos", () => {
    const { events } = parseSseChunk("data: {no-json}\n\n");
    expect(events).toEqual([]);
  });
});

describe("parseEnvLines", () => {
  it("convierte CLAVE=valor por línea, ignora vacías y conserva '=' en el valor", async () => {
    const { parseEnvLines } = await import("../lib/api");
    expect(parseEnvLines("A=1\r\n\n  B = x=y  \n")).toEqual({ A: "1", B: "x=y" });
  });
  it("rechaza líneas sin '='", async () => {
    const { parseEnvLines } = await import("../lib/api");
    expect(() => parseEnvLines("SOLO")).toThrow(/falta =/);
  });
});
