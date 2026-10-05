import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  dayOrdinal,
  formatBuiltLabel,
  formatBuiltTimestamp,
} from "./formatBuilt.ts";

describe("dayOrdinal", () => {
  it("covers 1st 2nd 3rd 4th and teen/rest edges", () => {
    assert.equal(dayOrdinal(1), "1st");
    assert.equal(dayOrdinal(2), "2nd");
    assert.equal(dayOrdinal(3), "3rd");
    assert.equal(dayOrdinal(4), "4th");
    assert.equal(dayOrdinal(11), "11th");
    assert.equal(dayOrdinal(12), "12th");
    assert.equal(dayOrdinal(13), "13th");
    assert.equal(dayOrdinal(21), "21st");
    assert.equal(dayOrdinal(22), "22nd");
    assert.equal(dayOrdinal(23), "23rd");
    assert.equal(dayOrdinal(31), "31st");
  });
});

describe("formatBuiltTimestamp", () => {
  it("formats the screen snapshot instant in UTC", () => {
    assert.equal(
      formatBuiltTimestamp("2026-10-04T03:20:25+00:00"),
      "Sunday, October 4th 2026 at 03:20 UTC",
    );
  });

  it("falls back for missing or invalid values", () => {
    assert.equal(formatBuiltTimestamp(null), "—");
    assert.equal(formatBuiltTimestamp(undefined), "—");
    assert.equal(formatBuiltTimestamp(""), "—");
    assert.equal(formatBuiltTimestamp("not-a-date"), "not-a-date");
  });
});

describe("formatBuiltLabel", () => {
  it("prefixes Built", () => {
    assert.equal(
      formatBuiltLabel("2026-10-04T03:20:25+00:00"),
      "Built Sunday, October 4th 2026 at 03:20 UTC",
    );
    assert.equal(formatBuiltLabel(null), "Built —");
  });
});
