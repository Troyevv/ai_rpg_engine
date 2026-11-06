import { describe, it, expect } from "vitest";
import {
  monthLength,
  shiftMonth,
  itemsOnDay,
  upcomingItems,
  statusLabel,
  type CalendarItem,
} from "../src/calendarView";
describe("calendar presentation without custom Date arithmetic", () => {
  it("Gregorian lengths include leap centuries and early years", () => {
    expect(
      [
        "2026-02",
        "2024-02",
        "1900-02",
        "2000-02",
        "0004-02",
        "2026-04",
        "2026-12",
      ].map((m) => monthLength(m)),
    ).toEqual([28, 29, 28, 29, 29, 30, 31]);
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(shiftMonth("2027-01", -1)).toBe("2026-12");
    expect(shiftMonth("0001-01", -1)).toBeNull();
    expect(shiftMonth("9999-12", 1)).toBeNull();
  });
  it("custom profiles cross years with their own month count and lengths", () => {
    const p = { system: "custom", month_lengths: [20, 25] };
    expect(monthLength("0042-02", p)).toBe(25);
    expect(shiftMonth("0042-02", 1, p)).toBe("0043-01");
    expect(shiftMonth("0043-01", -1, p)).toBe("0042-02");
    expect(shiftMonth("0042-02", 2, p)).toBe("0043-02");
  });
  it("interval markers include both boundaries; agenda excludes completed and cancelled plans", () => {
    const make = (
      id: string,
      extra: Partial<CalendarItem> = {},
    ): CalendarItem => ({
      id,
      date: "2026-10-08",
      kind: "commitment",
      name: id,
      character_ids: [],
      ...extra,
    });
    const items = [
      make("past", { date: "2026-10-07" }),
      make("active", {
        date: "2026-10-07",
        end_date: "2026-10-09",
        status: "pending",
      }),
      make("done", { status: "resolved" }),
      make("cancelled", { status: "cancelled" }),
      make("late", { window: { exact_time: "18:30" }, status: "pending" }),
      make("early", { window: { exact_time: "08:00" }, status: "pending" }),
    ];
    expect(itemsOnDay(items, "2026-10-09").map((e) => e.id)).toEqual([
      "active",
    ]);
    expect(itemsOnDay(items, "2026-10-10")).toEqual([]);
    expect(upcomingItems(items, "2026-10-08").map((e) => e.id)).toEqual([
      "active",
      "early",
      "late",
    ]);
    expect(
      statusLabel(
        make("overdue", {
          status: "pending",
          window: { relevance: "overdue" },
        }),
      ),
    ).toContain("срок прошёл");
  });
});
