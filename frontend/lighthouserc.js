module.exports = {
  ci: {
    collect: {
      url: [
        "http://localhost:8501/login",
        "http://localhost:8501/scoring",
        "http://localhost:8501/export",
        "http://localhost:8501/analysis",
        "http://localhost:8501/settings",
      ],
      numberOfRuns: 3,
      settings: {
        preset: "desktop",
        // Skip auth-required pages for now, test login page
        throttling: {
          cpuSlowdownMultiplier: 1,
        },
      },
    },
    assert: {
      assertions: {
        "categories:performance": ["error", { minScore: 0.7 }],
        "categories:best-practices": ["error", { minScore: 0.8 }],
        "categories:seo": ["warn", { minScore: 0.7 }],
        "first-contentful-paint": ["error", { maxNumericValue: 2000 }],
        "largest-contentful-paint": ["error", { maxNumericValue: 4000 }],
        "cumulative-layout-shift": ["error", { maxNumericValue: 0.1 }],
        "total-blocking-time": ["error", { maxNumericValue: 300 }],
        "categories:accessibility": ["error", { minScore: 0.9 }],
      },
    },
    upload: {
      target: "temporary-public-storage",
    },
  },
};
