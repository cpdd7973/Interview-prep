import js from "@eslint/js";
import security from "eslint-plugin-security";

export default [
  {
    ignores: ["node_modules/**", "dist/**"]
  },
  js.configs.recommended,
  security.configs.recommended,
  {
    plugins: { security },
    rules: {
      "no-console": "warn",
      "security/detect-non-literal-regexp": "warn",
      "security/detect-object-injection": "warn",
    },
  },
];