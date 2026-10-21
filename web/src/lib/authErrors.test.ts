import { describe, expect, it } from "vitest";
import { ApiError } from "./api/client";
import { authError } from "./authErrors";

describe("auth errors", () => {
  it("explains a failed sign-in without saying which half was wrong", () => {
    expect(authError(new ApiError(401, "unauthorized", "nope"), "sign-in")).toMatch(/don't match an account/);
    expect(authError(new TypeError("fetch failed"), "sign-in")).toMatch(/couldn't reach/);
  });

  it("tells a new owner what to change when sign-up is refused", () => {
    expect(authError(new ApiError(409, "conflict", "email is already registered"), "sign-up")).toMatch(/already an account/);
    expect(authError(new ApiError(400, "bad_request", "password must be 8 to 256 characters"), "sign-up")).toMatch(/8 and 256/);
    expect(authError(new ApiError(400, "bad_request", "email address is not valid"), "sign-up")).toMatch(/email address/);
    expect(authError(new ApiError(500, "internal", "boom"), "sign-up")).toMatch(/couldn't reach/);
  });
});
