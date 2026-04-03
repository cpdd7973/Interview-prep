import js from "@eslint/js";
import security from "eslint-plugin-security";
import globals from "globals";

export default [
  {
    ignores: ["node_modules/**", "dist/**"]
  },
  js.configs.recommended,
  security.configs.recommended,
  {
    plugins: { security },
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      "no-console": "warn",
      "security/detect-non-literal-regexp": "warn",
      "security/detect-object-injection": "warn",
    },
  },
];