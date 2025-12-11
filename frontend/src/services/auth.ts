import { type Configuration, PublicClientApplication, LogLevel } from "@azure/msal-browser"

// MSAL configuration
const msalConfig: Configuration = {
  auth: {
    clientId: import.meta.env.VITE_AZURE_CLIENT_ID || "",
    authority: `https://login.microsoftonline.com/${import.meta.env.VITE_AZURE_TENANT_ID || "common"}`,
    redirectUri: import.meta.env.VITE_REDIRECT_URI || window.location.origin,
    postLogoutRedirectUri: window.location.origin,
  },
  cache: {
    cacheLocation: "sessionStorage",
    storeAuthStateInCookie: false,
  },
  system: {
    loggerOptions: {
      loggerCallback: (level, message, containsPii) => {
        if (containsPii) {
          return
        }
        switch (level) {
          case LogLevel.Error:
            console.error(message)
            break
          case LogLevel.Warning:
            console.warn(message)
            break
          case LogLevel.Info:
            if (import.meta.env.DEV) {
              console.info(message)
            }
            break
          case LogLevel.Verbose:
            if (import.meta.env.DEV) {
              console.debug(message)
            }
            break
        }
      },
      logLevel: import.meta.env.DEV ? LogLevel.Verbose : LogLevel.Warning,
    },
  },
}

// Login request configuration
export const loginRequest = {
  scopes: [
    "openid",
    "profile",
    "email",
    // Add your API scope here
    import.meta.env.VITE_API_SCOPE || "api://infra-rag-api/access_as_user",
  ],
}

// API token request configuration
export const apiTokenRequest = {
  scopes: [import.meta.env.VITE_API_SCOPE || "api://infra-rag-api/access_as_user"],
}

// Create MSAL instance
export const msalInstance = new PublicClientApplication(msalConfig)

// Initialize MSAL
export async function initializeMsal(): Promise<void> {
  await msalInstance.initialize()

  // Handle redirect response
  const response = await msalInstance.handleRedirectPromise()
  if (response) {
    msalInstance.setActiveAccount(response.account)
  } else {
    // Check if there's already an active account
    const accounts = msalInstance.getAllAccounts()
    if (accounts.length > 0) {
      msalInstance.setActiveAccount(accounts[0])
    }
  }
}

// Get access token for API calls
export async function getAccessToken(): Promise<string | null> {
  const account = msalInstance.getActiveAccount()
  if (!account) {
    return null
  }

  try {
    const response = await msalInstance.acquireTokenSilent({
      ...apiTokenRequest,
      account,
    })
    return response.accessToken
  } catch (error) {
    // If silent token acquisition fails, fall back to interactive
    console.warn("Silent token acquisition failed, attempting interactive", error)
    try {
      const response = await msalInstance.acquireTokenPopup(apiTokenRequest)
      return response.accessToken
    } catch (interactiveError) {
      console.error("Interactive token acquisition failed", interactiveError)
      return null
    }
  }
}

// Login function
export async function login(): Promise<void> {
  try {
    const response = await msalInstance.loginPopup(loginRequest)
    msalInstance.setActiveAccount(response.account)
  } catch (error) {
    console.error("Login failed", error)
    throw error
  }
}

// Logout function
export async function logout(): Promise<void> {
  const account = msalInstance.getActiveAccount()
  if (account) {
    await msalInstance.logoutPopup({
      account,
      postLogoutRedirectUri: window.location.origin,
    })
  }
}

// Check if user is authenticated
export function isAuthenticated(): boolean {
  return msalInstance.getActiveAccount() !== null
}

// Get current user info
export function getCurrentUser() {
  const account = msalInstance.getActiveAccount()
  if (!account) {
    return null
  }
  return {
    id: account.localAccountId,
    name: account.name || account.username,
    email: account.username,
  }
}
