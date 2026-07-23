import { vi } from "vitest";

interface FetchCall {
  url: string;
  method: string;
  body: unknown;
  init?: RequestInit;
}

type RouteMatcher = string | RegExp | ((url: string, method: string) => boolean);
type RouteResponse =
  | unknown
  | ((call: FetchCall) => unknown | Promise<unknown>);

interface MockRoute {
  method?: string;
  path: RouteMatcher;
  response: RouteResponse;
  status?: number;
}

export function installFetchMock(routes: MockRoute[]) {
  const calls: FetchCall[] = [];
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = (init.method ?? "GET").toUpperCase();
      const body = await parseBody(init.body);
      const call: FetchCall = { url, method, body, init };
      calls.push(call);

      const route = routes.find((candidate) => {
        const expectedMethod = candidate.method?.toUpperCase() ?? "GET";
        return expectedMethod === method && matches(candidate.path, url, method);
      });

      if (!route) {
        return jsonResponse(
          { detail: `Unhandled ${method} ${url}` },
          { status: 500 },
        );
      }

      const response =
        typeof route.response === "function"
          ? await route.response(call)
          : route.response;
      return jsonResponse(response, { status: route.status ?? 200 });
    },
  );

  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

function matches(matcher: RouteMatcher, url: string, method: string): boolean {
  if (typeof matcher === "string") {
    return matcher === url;
  }
  if (matcher instanceof RegExp) {
    return matcher.test(url);
  }
  return matcher(url, method);
}

async function parseBody(body: BodyInit | null | undefined): Promise<unknown> {
  if (typeof body === "string") {
    try {
      return JSON.parse(body) as unknown;
    } catch {
      return body;
    }
  }
  if (body instanceof Blob) {
    return {
      blob_size: body.size,
      blob_type: body.type,
    };
  }
  if (body instanceof URLSearchParams) {
    return Object.fromEntries(body.entries());
  }
  return body ?? null;
}

function jsonResponse(body: unknown, init: ResponseInit): Response {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
}
