import { useMsal, useIsAuthenticated, useAccount } from "@azure/msal-react"
import { useCallback } from "react"
import { loginRequest, apiTokenRequest } from "@/services/auth"

export function useAuth() {
  const { instance, accounts } = useMsal()
  const isAuthenticated = useIsAuthenticated()
  const account = useAccount(accounts[0] || {})

  const login = useCallback(async () => {
    try {
      const response = await instance.loginPopup(loginRequest)
      instance.setActiveAccount(response.account)
    } catch (error) {
      console.error("Login failed", error)
      throw error
    }
  }, [instance])

  const logout = useCallback(async () => {
    try {
      await instance.logoutPopup({
        account: account || undefined,
        postLogoutRedirectUri: window.location.origin,
      })
    } catch (error) {
      console.error("Logout failed", error)
      throw error
    }
  }, [instance, account])

  const getAccessToken = useCallback(async (): Promise<string | null> => {
    if (!account) {
      return null
    }

    try {
      const response = await instance.acquireTokenSilent({
        ...apiTokenRequest,
        account,
      })
      return response.accessToken
    } catch (error) {
      console.warn("Silent token acquisition failed, attempting interactive", error)
      try {
        const response = await instance.acquireTokenPopup(apiTokenRequest)
        return response.accessToken
      } catch (interactiveError) {
        console.error("Interactive token acquisition failed", interactiveError)
        return null
      }
    }
  }, [instance, account])

  const user = account
    ? {
        id: account.localAccountId,
        name: account.name || account.username,
        email: account.username,
      }
    : null

  return {
    isAuthenticated,
    user,
    login,
    logout,
    getAccessToken,
  }
}
