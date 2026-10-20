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
