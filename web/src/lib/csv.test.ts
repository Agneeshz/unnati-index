import { describe, expect, it } from "vitest";
import { csvCell, toCsv } from "./csv";

describe("csv", () => {
  it("quotes only what needs quoting", () => {
    expect(csvCell("Keralam")).toBe("Keralam");
    expect(csvCell('Jaipur Greater (10,793) and "Heritage"')).toBe('"Jaipur Greater (10,793) and ""Heritage"""');
    expect(csvCell("two\nlines")).toBe('"two\nlines"');
    expect(csvCell(null)).toBe("");
    expect(csvCell(true)).toBe("yes");
    expect(csvCell(12.5)).toBe("12.5");
  });

  it("writes a BOM, a header and CRLF rows", () => {
    expect(toCsv(["a", "b"], [[1, "x,y"]])).toBe('﻿a,b\r\n1,"x,y"\r\n');
  });
});
