import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const config = [
  ...nextVitals,
  ...nextTypescript,
  {
    rules: {
      complexity: ["error", 8],
      "max-depth": ["error", 3],
      "max-lines-per-function": ["error", { max: 80, skipBlankLines: true, skipComments: true }],
    },
  },
  {
    files: ["**/*.test.ts", "**/*.test.tsx", "e2e/**"],
    rules: { "max-lines-per-function": "off" },
  },
  { ignores: [".next/**", ".next-server/**", "node_modules/**", "test-results/**", "playwright-report/**", "next-env.d.ts", "src/**/*.gen.ts"] },
];

export default config;
