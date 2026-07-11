/**
 * Django backend uchun proxy.
 * `/django-api/<...>` orqali kelgan barcha so'rovlar Django'ga uzatiladi.
 *
 * Sabab: brauzer to'g'ridan-to'g'ri backend'ga murojaat qilmaydi (CORS / mixed content).
 * Next.js server o'rtada turib so'rovni Django'ga uzatadi - bu CORS muammosini hal qiladi
 * va HTTPS (dev:https yoki production) bilan ham muammosiz ishlaydi.
 */
import { NextRequest } from "next/server";

const BACKEND_URL = (process.env.BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
]);

async function handler(
  req: NextRequest,
  context: { params: { path: string[] } } | { params: Promise<{ path: string[] }> }
) {
  // Next.js 14/15 ikkala variantni qo'llab-quvvatlash
  const p = (context.params instanceof Promise ? await context.params : context.params) as { path: string[] };
  const pathStr = (p.path || []).join("/");
  const url = new URL(req.url);
  // Django uchun oxiriga / qo'shamiz (APPEND_SLASH)
  const targetPath = pathStr.endsWith("/") ? pathStr : pathStr + "/";
  const target = `${BACKEND_URL}/api/${targetPath}${url.search}`;

  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  });

  const init: RequestInit = {
    method: req.method,
    headers,
    redirect: "manual",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  let res: Response;
  try {
    res = await fetch(target, init);
  } catch (e: any) {
    return new Response(
      JSON.stringify({ detail: `Backend bilan bog'lanib bo'lmadi: ${e.message}`, target }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }

  const respHeaders = new Headers();
  res.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) respHeaders.set(key, value);
  });

  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers: respHeaders,
  });
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
export const HEAD = handler;
export const OPTIONS = handler;

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
