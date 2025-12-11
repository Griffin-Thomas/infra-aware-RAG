# Infra-Aware RAG Frontend

React + TypeScript chat UI for the Infra-Aware RAG Assistant.

## Tech Stack

- **React 19** with TypeScript
- **Vite** for build tooling
- **Tailwind CSS v4** for styling
- **Shadcn/UI** component patterns (Radix primitives)
- **TanStack Query** (React Query) for data fetching
- **MSAL React** for Azure AD authentication
- **React Router** for navigation

## Prerequisites

- Node.js 18+
- npm 9+
- Backend API running (see main project README)

## Quick Start

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Configure Environment

Copy the example environment file and configure:

```bash
cp .env.example .env
```

Edit `.env` with your Azure AD configuration:

```env
# Azure AD Configuration
VITE_AZURE_CLIENT_ID=your-client-id
VITE_AZURE_AUTHORITY=https://login.microsoftonline.com/your-tenant-id
VITE_AZURE_REDIRECT_URI=http://localhost:5173

# API Configuration
VITE_API_BASE_URL=http://localhost:8000
```

### 3. Run Development Server

```bash
npm run dev
```

The app will be available at http://localhost:5173

### 4. Build for Production

```bash
npm run build
```

Production files are output to `dist/`.

## Project Structure

```
frontend/
├── src/
│   ├── components/       # React components
│   │   ├── Chat/         # Chat interface components
│   │   │   ├── ChatPage.tsx
│   │   │   ├── ChatContainer.tsx
│   │   │   ├── MessageList.tsx
│   │   │   ├── MessageItem.tsx
│   │   │   ├── InputBar.tsx
│   │   │   └── ToolCallDisplay.tsx
│   │   ├── Sidebar/      # Conversation sidebar
│   │   │   └── ConversationSidebar.tsx
│   │   ├── common/       # Shared components
│   │   │   ├── Header.tsx
│   │   │   ├── CodeBlock.tsx
│   │   │   ├── ResourceLink.tsx
│   │   │   └── LoadingIndicator.tsx
│   │   └── LoginPage.tsx
│   ├── hooks/            # Custom React hooks
│   │   ├── useAuth.ts    # Authentication hook
│   │   ├── useChat.ts    # Chat state management
│   │   └── useStream.ts  # SSE streaming hook
│   ├── services/         # API and auth services
│   │   ├── api.ts        # API client
│   │   └── auth.ts       # MSAL configuration
│   ├── types/            # TypeScript type definitions
│   │   └── index.ts
│   ├── lib/              # Utility functions
│   │   └── utils.ts
│   ├── App.tsx           # Root component with routing
│   ├── main.tsx          # Application entry point
│   └── index.css         # Global styles and Tailwind config
├── .env.example          # Environment template
├── package.json
├── tsconfig.json
├── vite.config.ts
└── README.md
```

## Azure AD Setup

1. Register an application in Azure Portal
2. Configure redirect URIs for your environment:
   - Development: `http://localhost:5173`
   - Production: Your deployed URL
3. Enable implicit grant for access tokens
4. Configure API permissions if needed
5. Copy the Client ID and Tenant ID to your `.env` file

## Backend Connection

The frontend expects the backend API to be running at `http://localhost:8000` by default. The Vite dev server proxies `/api` requests to the backend.

To run the backend:

```bash
# From project root
source .venv/bin/activate
uvicorn src.api.main:app --reload
```

## Available Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server |
| `npm run build` | Build for production |
| `npm run preview` | Preview production build |
| `npm run lint` | Run ESLint |

## Troubleshooting

### CORS Issues

If you see CORS errors, ensure:
1. The backend has CORS middleware configured for `http://localhost:5173`
2. You're using the Vite proxy (requests should go to `/api/...`, not the full backend URL)

### Authentication Issues

1. Verify Azure AD app registration is correct
2. Check redirect URI matches exactly (including trailing slashes)
3. Ensure the tenant ID is correct in the authority URL

### API Connection Issues

1. Confirm the backend is running on port 8000
2. Check the browser console for network errors
3. Verify the Vite proxy is configured correctly in `vite.config.ts`
