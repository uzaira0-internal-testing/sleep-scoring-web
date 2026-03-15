/**
 * Tests for content-hash.ts — SHA-256 hashing utilities.
 */
import { describe, it, expect } from "bun:test";
import { toHex, sha256Hex, computeMarkerHash, computeFileHash } from "./content-hash";

describe("toHex", () => {
  it("converts empty buffer to empty string", () => {
    expect(toHex(new ArrayBuffer(0))).toBe("");
  });

  it("converts single byte", () => {
    const buf = new Uint8Array([0xff]).buffer;
    expect(toHex(buf)).toBe("ff");
  });

  it("zero-pads single digit hex values", () => {
    const buf = new Uint8Array([0x0a, 0x01]).buffer;
    expect(toHex(buf)).toBe("0a01");
  });

  it("converts multiple bytes", () => {
    const buf = new Uint8Array([0xde, 0xad, 0xbe, 0xef]).buffer;
    expect(toHex(buf)).toBe("deadbeef");
  });
});

describe("sha256Hex", () => {
  it("hashes empty string", async () => {
    const hash = await sha256Hex("");
    // Known SHA-256 of empty string
    expect(hash).toBe("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  });

  it("hashes 'hello'", async () => {
    const hash = await sha256Hex("hello");
    expect(hash).toBe("2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824");
  });

  it("returns consistent results for same input", async () => {
    const h1 = await sha256Hex("test");
    const h2 = await sha256Hex("test");
    expect(h1).toBe(h2);
  });

  it("returns different results for different inputs", async () => {
    const h1 = await sha256Hex("input1");
    const h2 = await sha256Hex("input2");
    expect(h1).not.toBe(h2);
  });

  it("returns 64-character hex string", async () => {
    const hash = await sha256Hex("anything");
    expect(hash).toHaveLength(64);
    expect(/^[0-9a-f]{64}$/.test(hash)).toBe(true);
  });
});

describe("computeMarkerHash", () => {
  it("returns consistent hash for same marker data", async () => {
    const data = {
      sleepMarkers: [{ onsetTimestamp: 100, offsetTimestamp: 200, markerIndex: 1, markerType: "MAIN_SLEEP" as const }],
      nonwearMarkers: [],
      isNoSleep: false,
      notes: "test",
    };
    const h1 = await computeMarkerHash(data);
    const h2 = await computeMarkerHash(data);
    expect(h1).toBe(h2);
  });

  it("returns same hash regardless of marker array order", async () => {
    const data1 = {
      sleepMarkers: [
        { onsetTimestamp: 100, offsetTimestamp: 200, markerIndex: 1, markerType: "MAIN_SLEEP" as const },
        { onsetTimestamp: 300, offsetTimestamp: 400, markerIndex: 2, markerType: "NAP" as const },
      ],
      nonwearMarkers: [],
      isNoSleep: false,
      notes: "",
    };
    const data2 = {
      sleepMarkers: [
        { onsetTimestamp: 300, offsetTimestamp: 400, markerIndex: 2, markerType: "NAP" as const },
        { onsetTimestamp: 100, offsetTimestamp: 200, markerIndex: 1, markerType: "MAIN_SLEEP" as const },
      ],
      nonwearMarkers: [],
      isNoSleep: false,
      notes: "",
    };
    const h1 = await computeMarkerHash(data1);
    const h2 = await computeMarkerHash(data2);
    expect(h1).toBe(h2);
  });

  it("different markers produce different hashes", async () => {
    const h1 = await computeMarkerHash({
      sleepMarkers: [{ onsetTimestamp: 100, offsetTimestamp: 200, markerIndex: 1, markerType: "MAIN_SLEEP" as const }],
      nonwearMarkers: [],
      isNoSleep: false,
      notes: "",
    });
    const h2 = await computeMarkerHash({
      sleepMarkers: [{ onsetTimestamp: 100, offsetTimestamp: 300, markerIndex: 1, markerType: "MAIN_SLEEP" as const }],
      nonwearMarkers: [],
      isNoSleep: false,
      notes: "",
    });
    expect(h1).not.toBe(h2);
  });

  it("isNoSleep affects hash", async () => {
    const base = {
      sleepMarkers: [],
      nonwearMarkers: [],
      notes: "",
    };
    const h1 = await computeMarkerHash({ ...base, isNoSleep: false });
    const h2 = await computeMarkerHash({ ...base, isNoSleep: true });
    expect(h1).not.toBe(h2);
  });
});

describe("computeFileHash", () => {
  it("hashes first 64KB of file", async () => {
    const content = "x".repeat(100);
    const file = new File([content], "test.csv");
    const hash = await computeFileHash(file);
    expect(hash).toHaveLength(64);
    expect(/^[0-9a-f]{64}$/.test(hash)).toBe(true);
  });

  it("returns consistent hash for same content", async () => {
    const file1 = new File(["same content"], "a.csv");
    const file2 = new File(["same content"], "b.csv");
    const h1 = await computeFileHash(file1);
    const h2 = await computeFileHash(file2);
    expect(h1).toBe(h2);
  });

  it("returns different hash for different content", async () => {
    const file1 = new File(["content A"], "a.csv");
    const file2 = new File(["content B"], "b.csv");
    const h1 = await computeFileHash(file1);
    const h2 = await computeFileHash(file2);
    expect(h1).not.toBe(h2);
  });
});
