import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { KaiCore } from "../components/KaiCore";
import { FuturePage } from "../components/ui";

describe("KaiCore", () => {
  it("refleja el estado en atributos y etiqueta accesible", () => {
    render(<KaiCore state="processing" />);
    const el = screen.getByRole("img");
    expect(el.getAttribute("data-state")).toBe("processing");
    expect(el.getAttribute("aria-label")).toContain("Procesando");
  });
});

describe("FuturePage", () => {
  it("marca la función como no disponible", () => {
    render(<FuturePage title="Voz" phase={2} description="d" items={["a"]} />);
    expect(screen.getByText("No disponible todavía")).toBeTruthy();
    expect(screen.getByText("Función futura — Fase 2")).toBeTruthy();
  });
});
