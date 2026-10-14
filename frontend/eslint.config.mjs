import tseslint from "typescript-eslint";
import hooks from "eslint-plugin-react-hooks";
export default [
  {
    ignores: [".next/**", "node_modules/**", "coverage/**", "test-results/**"],
  },
  {
    files: ["**/*.ts", "**/*.tsx"],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: { "@typescript-eslint": tseslint.plugin, "react-hooks": hooks },
    rules: {
      "no-eval": "error",
      "no-implied-eval": "error",
      eqeqeq: "error",
      "@typescript-eslint/no-explicit-any": "error",
      "react-hooks/rules-of-hooks": "error",
    },
  },
];
