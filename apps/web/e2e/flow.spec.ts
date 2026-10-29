import { expect, test, type Browser, type Page } from "@playwright/test";

const PASSWORD = process.env.E2E_PASSWORD ?? "";
const errors: string[] = [];

async function login(browser: Browser, email: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  page.on("pageerror", (e) => errors.push(`${email} ${page.url()}: ${e.message}`));
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button:has-text("Entrar")');
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Concentrado de 8D" })).toBeVisible();
  return page;
}

test.beforeAll(() => {
  expect(PASSWORD, "Define E2E_PASSWORD").not.toBe("");
});

test("ingeniería crea un caso, completa D0 y calidad lo aprueba", async ({ browser }) => {
  const ing = await login(browser, "ingenieria@demo.local");
  await ing.goto("/casos?nuevo=1");
  await ing.getByLabel("Título del problema").fill("E2E: rebaba en carcasa");
  await expect(ing.getByRole("button", { name: "Crear caso" })).toBeDisabled();  // falta elegir interno/externo
  await ing.getByRole("radio", { name: /8D interno/ }).click();
  await ing.getByLabel("Origen").selectOption("internal");
  await ing.click('button:has-text("Crear caso")');
  await expect(ing).toHaveURL(/\/casos\/[0-9a-f-]{36}$/);
  const caseUrl = ing.url();
  await expect(ing.locator(".page-head .badge.navy")).toContainText("8D-PLT1-");

  // Requisito pendiente visible y envío deshabilitado.
  const submit = ing.getByRole("button", { name: "Enviar a revisión" });
  await expect(submit).toBeDisabled();
  await ing.getByLabel(/Acciones de respuesta de emergencia/).fill("Bloqueo de 3 lotes en almacén");
  await ing.getByLabel("¿Por qué se requiere un 8D?").fill("Defecto recurrente con impacto en cliente");
  await ing.click('button:has-text("Guardar borrador")');
  await expect(ing.getByText("Guardado")).toBeVisible();
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect(ing.locator(".card-head .badge").filter({ hasText: "En revisión" })).toBeVisible();
  // El ingeniero no ve el botón de aprobar.
  await expect(ing.getByRole("button", { name: "Aprobar" })).toHaveCount(0);

  // Persistencia tras recargar.
  await ing.reload();
  await expect(ing.getByLabel(/Acciones de respuesta de emergencia/)).toHaveValue("Bloqueo de 3 lotes en almacén");

  const mgr = await login(browser, "calidad@demo.local");
  await mgr.goto(caseUrl);
  await mgr.getByRole("button", { name: "Aprobar" }).click();
  await mgr.getByRole("dialog").getByRole("button", { name: "Aprobar" }).click();
  await expect(mgr.locator(".card-head .badge").filter({ hasText: "Aprobada" })).toBeVisible();
  await expect(mgr.getByText("1 / 9")).toBeVisible();

  // Documento real desde la pestaña de documentos.
  await mgr.getByRole("tab", { name: "Documentos y archivos" }).click();
  await mgr.locator("tr", { hasText: "Reporte de avance" }).getByRole("button", { name: "Emitir PDF" }).click();
  await expect(mgr.locator(".notice.ok")).toContainText("_Avance_rev1.pdf");
  const href = await mgr.locator(".notice.ok a").getAttribute("href");
  const pdf = await mgr.request.get(href!);
  expect(pdf.headers()["content-type"]).toBe("application/pdf");
  expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");

  // Bitácora con la aprobación.
  await mgr.getByRole("tab", { name: "Bitácora" }).click();
  await expect(mgr.getByText("Disciplina aprobada")).toBeVisible();
  await expect(mgr.getByText("Documento emitido")).toBeVisible();
});

test("consulta solo lee y reportes muestran indicadores definidos", async ({ browser }) => {
  const viewer = await login(browser, "consulta@demo.local");
  await viewer.goto("/casos");
  await expect(viewer.getByRole("button", { name: "+ Nuevo caso" })).toHaveCount(0);
  await expect(viewer.getByText("E2E: rebaba en carcasa")).toBeVisible();
  await viewer.goto("/admin");
  await expect(viewer.getByText("Esta sección requiere el rol de administrador.")).toBeVisible();
  const forbidden = await viewer.request.post("/api/cases", { headers: { "x-d8-client": "web" }, data: { title: "x" } });
  expect(forbidden.status()).toBe(403);

  await viewer.goto("/reportes");
  await expect(viewer.getByText("Casos abiertos").first()).toBeVisible();
  await expect(viewer.getByText("Datos insuficientes").first()).toBeVisible();
  await viewer.getByText("Definición de los indicadores").click();
  await expect(viewer.getByText("Tiempo de resolución").last()).toBeVisible();
  await viewer.goto("/lecciones");
  await expect(viewer.getByText("Lecciones publicadas.")).toBeVisible();

  await viewer.click('button:has-text("Salir")');
  await expect(viewer).toHaveURL(/\/login/);
  await viewer.goto("/casos");
  await expect(viewer).toHaveURL(/\/login\?next=%2Fcasos/);
});

test.afterAll(() => {
  expect(errors, errors.join("\n")).toEqual([]);
});
