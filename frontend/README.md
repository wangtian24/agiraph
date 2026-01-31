# AI Agent Orchestration Framework - Frontend

Next.js frontend for the AI Agent Orchestration Framework.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Make sure the backend is running on `http://localhost:8000`

3. Start the development server:
```bash
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000) in your browser

## Features

- **Markdown Rendering**: All node results are rendered as proper markdown with syntax highlighting
- **DAG Visualization**: Interactive graph visualization using ReactFlow
- **Real-time Updates**: WebSocket support for live execution status
- **Left-aligned Content**: Proper text alignment (not center-aligned)
- **Modern UI**: Clean, dark-themed interface with Tailwind CSS

## Tech Stack

- Next.js 14
- React 18
- TypeScript
- Tailwind CSS
- ReactFlow (for DAG visualization)
- react-markdown (for markdown rendering)
- Axios (for API calls)
