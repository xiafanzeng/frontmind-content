import { z } from "zod";

export type AgentProvider = "manus" | "zhipu" | "xty_codex" | "tencent_wma" | "kimi";
export type AgentUpstreamEffort = "low" | "medium" | "high" | "max";

export const managedAgentProfileSchema = z.enum([
  "frontmind-base",
  "frontmind-pro",
]);

export type ManagedAgentProfile = z.infer<typeof managedAgentProfileSchema>;

export const DEFAULT_MANAGED_AGENT_PROFILE: ManagedAgentProfile =
  "frontmind-pro";

export function normalizeManagedAgentProfile(
  value: unknown,
): ManagedAgentProfile {
  return value === "frontmind-base"
    ? "frontmind-base"
    : DEFAULT_MANAGED_AGENT_PROFILE;
}

export function managedAgentProfileModel(
  profile: ManagedAgentProfile,
): "manus-1.6" | "manus-1.6-max";
export function managedAgentProfileModel(
  profile: ManagedAgentProfile,
  provider: AgentProvider,
): "manus-1.6" | "manus-1.6-max" | "glm-5.3" | "gpt-5.6-sol" | "deepseek-v4-pro" | "kimi-k3.1-pro";
export function managedAgentProfileModel(
  profile: ManagedAgentProfile,
  provider: AgentProvider = "manus",
) {
  if (provider === "kimi") return "kimi-k3.1-pro";
  if (provider === "zhipu") return "glm-5.3";
  if (provider === "xty_codex") return "gpt-5.6-sol";
  if (provider === "tencent_wma") return "deepseek-v4-pro";
  return profile === "frontmind-base" ? "manus-1.6" : "manus-1.6-max";
}

export function managedAgentProfileEffort(
  profile: ManagedAgentProfile,
): AgentUpstreamEffort {
  return profile === "frontmind-base" ? "high" : "max";
}

/**
 * Public model choice for the delivery administrator/engineer general Agent.
 * This is deliberately separate from a customer's Base/Pro service profile:
 * an internal Key authenticates the request while each new Agent task freezes
 * its own Lite/Base/Pro choice.
 */
export const generalAgentModelProfileSchema = z.enum([
  "frontmind-lite",
  "frontmind-base",
  "frontmind-pro",
]);

export type GeneralAgentModelProfile = z.infer<
  typeof generalAgentModelProfileSchema
>;

export const DEFAULT_GENERAL_AGENT_MODEL_PROFILE: GeneralAgentModelProfile =
  "frontmind-pro";

export function generalAgentModelProfileModel(
  profile: GeneralAgentModelProfile,
): "manus-1.6-lite" | "manus-1.6" | "manus-1.6-max";
export function generalAgentModelProfileModel(
  profile: GeneralAgentModelProfile,
  provider: AgentProvider,
): "manus-1.6-lite" | "manus-1.6" | "manus-1.6-max" | "glm-5.3" | "gpt-5.6-sol" | "kimi-k3.1-pro";
export function generalAgentModelProfileModel(
  profile: GeneralAgentModelProfile,
  provider: AgentProvider = "manus",
) {
  if (provider === "kimi") return "kimi-k3.1-pro";
  if (provider === "zhipu") return "glm-5.3";
  if (provider === "xty_codex") return "gpt-5.6-sol";
  if (provider === "tencent_wma") throw new Error("WMA_KNOWLEDGE_ONLY");
  if (profile === "frontmind-lite") return "manus-1.6-lite" as const;
  if (profile === "frontmind-base") return "manus-1.6" as const;
  return "manus-1.6-max" as const;
}

export function generalAgentModelProfileEffort(
  profile: GeneralAgentModelProfile,
): AgentUpstreamEffort {
  if (profile === "frontmind-lite") return "low";
  return profile === "frontmind-base" ? "high" : "max";
}
