module.exports = {
  testEnvironment: 'node',
  roots: ['<rootDir>/test'],
  testMatch: ['**/*.test.ts'],
  // Resolve .ts before .js: stale `tsc` output in lib/ (gitignored) would
  // otherwise shadow the sources and make local guardrail runs test old code.
  moduleFileExtensions: ['ts', 'tsx', 'js', 'json'],
  transform: { '^.+\\.tsx?$': 'ts-jest' },
};
