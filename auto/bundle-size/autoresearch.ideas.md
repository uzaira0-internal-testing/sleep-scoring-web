# Autoresearch Ideas: Bundle Size

## Dead Ends (tried and failed)

## Key Insights

## Remaining Ideas
- Tree-shake unused lucide-react icons (named imports only)
- Dynamic import heavy routes (React.lazy)
- Analyze date-fns — use subpath imports instead of full import
- Check if react-resizable-panels is used or can be lighter
- Evaluate if @tanstack/react-query needs full bundle
- Move Storybook deps to devDependencies if not already
- Check for duplicate dependencies in bundle
- Externalize large deps (uplot?) and load from CDN
- Split vendor chunks strategically
- Remove dead exports from services/
- Check if zod v4 has better tree-shaking than v3
- Analyze Comlink/worker bundle — maybe inline
