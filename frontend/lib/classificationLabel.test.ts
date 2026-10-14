import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  classificationLabel,
  classificationSchemeLabel,
  type ClassificationBlock,
} from "./classificationLabel.ts";

describe("classificationLabel", () => {
  it("formats GICS sector and sub-industry", () => {
    const block: ClassificationBlock = {
      scheme: "gics",
      sector: "Information Technology",
      industry: "Technology Hardware, Storage & Peripherals",
      link: "/screen?sector=Information%20Technology",
    };
    assert.equal(
      classificationLabel(block),
      "Information Technology · Technology Hardware, Storage & Peripherals",
    );
    assert.equal(classificationSchemeLabel(block), "GICS");
  });

  it("formats SIC with division and description", () => {
    const block: ClassificationBlock = {
      scheme: "sic",
      sector: "Manufacturing",
      industry: "Motor Vehicles & Passenger Car Bodies",
      sic: 3711,
      link: null,
    };
    assert.equal(
      classificationLabel(block),
      "Manufacturing · Motor Vehicles & Passenger Car Bodies (SIC 3711)",
    );
    assert.equal(classificationSchemeLabel(block), "SEC SIC");
  });

  it("returns null when nothing to show", () => {
    assert.equal(classificationLabel(null), null);
    assert.equal(classificationLabel({ scheme: "gics" }), null);
  });
});
