import "@testing-library/jest-dom";

// jsdom has no object-URL implementation, and the composer builds one for every
// attachment preview it shows.
if (!URL.createObjectURL) {
  URL.createObjectURL = () => "blob:hitrendy-test";
}
if (!URL.revokeObjectURL) {
  URL.revokeObjectURL = () => undefined;
}
