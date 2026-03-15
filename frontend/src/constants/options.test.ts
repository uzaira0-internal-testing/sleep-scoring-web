import { describe, it, expect } from "bun:test";
import {
  MARKER_LIMITS,
  ACTIVITY_SOURCE_OPTIONS,
  ALGORITHM_OPTIONS,
  DETECTION_RULE_PARAMS,
  getDetectionRuleParams,
  SLEEP_DETECTION_OPTIONS,
  MARKER_TYPE_OPTIONS,
  VIEW_MODE_OPTIONS,
} from "./options";
import { ALGORITHM_TYPES, SLEEP_DETECTION_RULES } from "@/api/types";

describe("MARKER_LIMITS", () => {
  it("defines MAX_SLEEP_PERIODS_PER_DAY", () => {
    expect(MARKER_LIMITS.MAX_SLEEP_PERIODS_PER_DAY).toBe(4);
  });

  it("defines MAX_NONWEAR_PERIODS_PER_DAY", () => {
    expect(MARKER_LIMITS.MAX_NONWEAR_PERIODS_PER_DAY).toBe(10);
  });

  it("defines EPOCH_DURATION_SECONDS", () => {
    expect(MARKER_LIMITS.EPOCH_DURATION_SECONDS).toBe(60);
  });
});

describe("ACTIVITY_SOURCE_OPTIONS", () => {
  it("has 4 axis options", () => {
    expect(ACTIVITY_SOURCE_OPTIONS).toHaveLength(4);
  });

  it("includes vector_magnitude", () => {
    const vm = ACTIVITY_SOURCE_OPTIONS.find((o) => o.value === "vector_magnitude");
    expect(vm).toBeDefined();
    expect(vm!.label).toContain("Vector Magnitude");
  });
});

describe("ALGORITHM_OPTIONS", () => {
  it("has 4 algorithm options", () => {
    expect(ALGORITHM_OPTIONS).toHaveLength(4);
  });

  it("includes sadeh_1994_actilife as first (recommended)", () => {
    expect(ALGORITHM_OPTIONS[0]!.value).toBe(ALGORITHM_TYPES.SADEH_1994_ACTILIFE);
    expect(ALGORITHM_OPTIONS[0]!.label).toContain("Recommended");
  });

  it("includes all algorithm types", () => {
    const values = ALGORITHM_OPTIONS.map((o) => o.value);
    expect(values).toContain(ALGORITHM_TYPES.SADEH_1994_ACTILIFE);
    expect(values).toContain(ALGORITHM_TYPES.SADEH_1994_ORIGINAL);
    expect(values).toContain(ALGORITHM_TYPES.COLE_KRIPKE_1992_ACTILIFE);
    expect(values).toContain(ALGORITHM_TYPES.COLE_KRIPKE_1992_ORIGINAL);
  });
});

describe("DETECTION_RULE_PARAMS", () => {
  it("defines params for 3S/5S rule", () => {
    const params = DETECTION_RULE_PARAMS[SLEEP_DETECTION_RULES.CONSECUTIVE_3S_5S];
    expect(params).toBeDefined();
    expect(params!.onsetN).toBe(3);
    expect(params!.offsetN).toBe(5);
    expect(params!.offsetState).toBe("sleep");
  });

  it("defines params for 5S/10S rule", () => {
    const params = DETECTION_RULE_PARAMS[SLEEP_DETECTION_RULES.CONSECUTIVE_5S_10S];
    expect(params).toBeDefined();
    expect(params!.onsetN).toBe(5);
    expect(params!.offsetN).toBe(10);
  });

  it("defines params for Tudor-Locke 2014", () => {
    const params = DETECTION_RULE_PARAMS[SLEEP_DETECTION_RULES.TUDOR_LOCKE_2014];
    expect(params).toBeDefined();
    expect(params!.offsetState).toBe("wake");
  });
});

describe("getDetectionRuleParams", () => {
  it("returns params for known rule", () => {
    const params = getDetectionRuleParams(SLEEP_DETECTION_RULES.CONSECUTIVE_3S_5S);
    expect(params.onsetN).toBe(3);
    expect(params.offsetN).toBe(5);
  });

  it("returns default params for unknown rule", () => {
    const params = getDetectionRuleParams("unknown_rule");
    expect(params.onsetN).toBe(3);
    expect(params.offsetN).toBe(5);
    expect(params.offsetState).toBe("sleep");
  });
});

describe("SLEEP_DETECTION_OPTIONS", () => {
  it("has 3 options", () => {
    expect(SLEEP_DETECTION_OPTIONS).toHaveLength(3);
  });

  it("each option has value and label", () => {
    for (const opt of SLEEP_DETECTION_OPTIONS) {
      expect(opt.value).toBeTruthy();
      expect(opt.label).toBeTruthy();
    }
  });
});

describe("MARKER_TYPE_OPTIONS", () => {
  it("has 2 marker type options", () => {
    expect(MARKER_TYPE_OPTIONS).toHaveLength(2);
  });

  it("includes MAIN_SLEEP and NAP", () => {
    const values = MARKER_TYPE_OPTIONS.map((o) => o.value);
    expect(values).toContain("MAIN_SLEEP");
    expect(values).toContain("NAP");
  });
});

describe("VIEW_MODE_OPTIONS", () => {
  it("has 2 view mode options (24h, 48h)", () => {
    expect(VIEW_MODE_OPTIONS).toHaveLength(2);
    expect(VIEW_MODE_OPTIONS[0]!.value).toBe("24");
    expect(VIEW_MODE_OPTIONS[1]!.value).toBe("48");
  });
});
