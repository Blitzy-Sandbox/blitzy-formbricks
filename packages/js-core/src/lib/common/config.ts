import { JS_LOCAL_STORAGE_KEY } from "@/lib/common/constants";
import { wrapThrows } from "@/lib/common/utils";
import type { TConfig, TConfigUpdateInput } from "@/types/config";
import { type Result, err, ok } from "@/types/error";

/**
 * Singleton that persists **runtime** survey/environment state (`TConfig`) to localStorage.
 *
 * Important architectural note: this class handles `TConfig` / `TConfigUpdateInput` only.
 * It does NOT store or manage `TConfigInput` — the initialization-time input that now
 * includes optional embed-mode fields (`embedMode`, `sliderConfig`, `popoverConfig`,
 * `sideTabConfig`). Those settings are consumed once during `setup()` (see setup.ts) to
 * create the appropriate DOM structures and are never persisted through the Config
 * singleton. This separation keeps the localStorage footprint lean and avoids stale
 * embed-mode data surviving across page navigations.
 */
export class Config {
  private static instance: Config | null = null;
  private config: TConfig | null = null;

  private constructor() {
    const savedConfig = this.loadFromLocalStorage();

    if (savedConfig.ok) {
      this.config = savedConfig.data;
    }
  }

  static getInstance(): Config {
    Config.instance ??= new Config();
    return Config.instance;
  }

  /**
   * Merges incoming runtime state into the stored `TConfig` and persists to localStorage.
   * Only `TConfigUpdateInput` fields are accepted — embed-mode configuration from
   * `TConfigInput` is intentionally excluded because it is an initialization-time concern
   * handled in setup.ts, not a runtime persistence concern.
   */
  public update(newConfig: TConfigUpdateInput): void {
    this.config = {
      ...this.config,
      ...newConfig,
      status: {
        value: newConfig.status?.value ?? "success",
        expiresAt: newConfig.status?.expiresAt ?? null,
      },
    };

    void this.saveToStorage();
  }

  public get(): TConfig {
    if (!this.config) {
      throw new Error("config is null, maybe the init function was not called?");
    }
    return this.config;
  }

  public loadFromLocalStorage(): Result<TConfig> {
    if (typeof window !== "undefined") {
      const savedConfig = localStorage.getItem(JS_LOCAL_STORAGE_KEY);
      if (savedConfig) {
        // TODO: validate config
        // This is a hack to get around the fact that we don't have a proper
        // way to validate the config yet.
        const parsedConfig = JSON.parse(savedConfig) as TConfig;
        return ok(parsedConfig);
      }
    }

    return err(new Error("No or invalid config in local storage"));
  }

  private saveToStorage(): Result<void> {
    return wrapThrows(() => {
      localStorage.setItem(JS_LOCAL_STORAGE_KEY, JSON.stringify(this.config));
    })();
  }

  // reset the config

  public resetConfig(): Result<void> {
    this.config = null;

    return wrapThrows(() => {
      localStorage.removeItem(JS_LOCAL_STORAGE_KEY);
    })();
  }
}
