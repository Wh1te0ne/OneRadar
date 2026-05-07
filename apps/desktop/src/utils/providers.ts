import type { ApiProvider } from "../api";

export type ProviderCapability = "llm" | "asr";

export function providerCapability(provider: ApiProvider): ProviderCapability {
  if (provider.capability === "asr" || provider.capability === "llm") return provider.capability;
  if ((provider.transcription_model || provider.transcription_app_id) && !provider.chat_model) return "asr";
  return "llm";
}

export function hasConfiguredLlmProvider(providers: ApiProvider[]) {
  return providers.some((provider) =>
    providerCapability(provider) === "llm"
    && provider.is_enabled
    && Boolean(provider.base_url)
    && Boolean(provider.chat_model)
    && Boolean(provider.api_key_configured)
  );
}

export function hasConfiguredAsrProvider(providers: ApiProvider[]) {
  return providers.some((provider) =>
    providerCapability(provider) === "asr"
    && provider.is_enabled
    && Boolean(provider.transcription_app_id)
    && Boolean(provider.transcription_model)
    && Boolean(provider.transcription_access_token_configured)
    && Boolean(provider.transcription_secret_key_configured)
  );
}
