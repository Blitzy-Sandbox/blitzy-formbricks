/* eslint-disable @typescript-eslint/unbound-method -- required for testing */
/* eslint-disable @typescript-eslint/no-unsafe-assignment -- vi.fn() returns any in test mocks */
/* eslint-disable @typescript-eslint/no-unnecessary-condition -- runtime conditions differ from static analysis in mocked environments */
import { type Mock, type MockInstance, afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { Config } from "@/lib/common/config";
import { JS_LOCAL_STORAGE_KEY } from "@/lib/common/constants";
import { addCleanupEventListeners, addEventListeners } from "@/lib/common/event-listeners";
import { Logger } from "@/lib/common/logger";
import { handleErrorOnFirstSetup, putFormbricksInErrorState, setup, tearDown } from "@/lib/common/setup";
import { setIsSetup } from "@/lib/common/status";
import { filterSurveys, getIsDebug, isNowExpired } from "@/lib/common/utils";
import type * as Utils from "@/lib/common/utils";
import { fetchEnvironmentState } from "@/lib/environment/state";
import { DEFAULT_USER_STATE_NO_USER_ID } from "@/lib/user/state";
import { sendUpdatesToBackend } from "@/lib/user/update";

const setItemMock = localStorage.setItem as unknown as Mock;

// 2) Mock Config
vi.mock("@/lib/common/config", () => ({
  JS_LOCAL_STORAGE_KEY: "formbricks-js",
  Config: {
    getInstance: vi.fn(() => ({
      get: vi.fn(),
      update: vi.fn(),
      resetConfig: vi.fn(),
    })),
  },
}));

// 3) Mock logger
vi.mock("@/lib/common/logger", () => ({
  Logger: {
    getInstance: vi.fn(() => ({
      debug: vi.fn(),
      error: vi.fn(),
      configure: vi.fn(),
    })),
  },
}));

// 4) Mock event-listeners
vi.mock("@/lib/common/event-listeners", () => ({
  addEventListeners: vi.fn(),
  addCleanupEventListeners: vi.fn(),
  removeAllEventListeners: vi.fn(),
}));

// 5) Mock fetchEnvironmentState
vi.mock("@/lib/environment/state", () => ({
  fetchEnvironmentState: vi.fn(),
}));

// 6) Mock filterSurveys
vi.mock("@/lib/common/utils", async (importOriginal) => {
  const originalModule = await importOriginal<typeof Utils>();
  return {
    ...originalModule,
    filterSurveys: vi.fn(),
    isNowExpired: vi.fn(),
    getIsDebug: vi.fn(),
  };
});

// 7) Mock user/update
vi.mock("@/lib/user/update", () => ({
  sendUpdatesToBackend: vi.fn(),
}));

// 8) Mock checkPageUrl
vi.mock("@/lib/survey/no-code-action", () => ({
  checkPageUrl: vi.fn(),
}));

// 9) Mock closeSurvey (used by tearDown and putFormbricksInErrorState)
vi.mock("@/lib/survey/widget", () => ({
  closeSurvey: vi.fn(),
}));

describe("setup.ts", () => {
  let getInstanceConfigMock: MockInstance<() => Config>;
  let getInstanceLoggerMock: MockInstance<() => Logger>;

  const mockLogger = {
    debug: vi.fn(),
    error: vi.fn(),
    configure: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    // By default, set isSetup to false so we can test setup logic from scratch
    setIsSetup(false);

    getInstanceConfigMock = vi.spyOn(Config, "getInstance");
    getInstanceLoggerMock = vi.spyOn(Logger, "getInstance").mockReturnValue(mockLogger as unknown as Logger);
    (getIsDebug as unknown as Mock).mockReturnValue(false);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    // Clean up any DOM elements created by embed mode tests
    const ids = [
      "formbricks-slider-container",
      "formbricks-popover-container",
      "formbricks-popover-button",
      "formbricks-side-tab-container",
      "formbricks-side-tab-button",
    ];
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) el.remove();
    }
  });

  describe("setup()", () => {
    test("returns ok if already setup", async () => {
      getInstanceLoggerMock.mockReturnValue(mockLogger as unknown as Logger);
      setIsSetup(true);
      const result = await setup({ environmentId: "env_id", appUrl: "https://my.url" });
      expect(result.ok).toBe(true);
      expect(mockLogger.debug).toHaveBeenCalledWith("Already set up, skipping setup.");
    });

    test("fails if no environmentId is provided", async () => {
      const result = await setup({ environmentId: "", appUrl: "https://my.url" });
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.error.code).toBe("missing_field");
      }
    });

    test("fails if no appUrl is provided", async () => {
      const result = await setup({ environmentId: "env_123", appUrl: "" });
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.error.code).toBe("missing_field");
      }
    });

    test("skips setup if existing config is in error state and not expired (debug mode)", async () => {
      (getIsDebug as unknown as Mock).mockReturnValue(true);
      const mockConfig = {
        get: vi.fn().mockReturnValue({
          environmentId: "env_123",
          appUrl: "https://my.url",
          environment: {},
          user: { data: {}, expiresAt: null },
          status: { value: "error", expiresAt: new Date(Date.now() + 10000) },
        }),
        resetConfig: vi.fn(),
      };

      getInstanceConfigMock.mockReturnValue(mockConfig as unknown as Config);

      (isNowExpired as unknown as Mock).mockReturnValue(false); // Not expired

      const result = await setup({ environmentId: "env_123", appUrl: "https://my.url" });
      expect(result.ok).toBe(true);
      expect(mockLogger.debug).toHaveBeenCalledWith(
        "Formbricks is in error state, but debug mode is active. Resetting config and continuing."
      );
    });

    test("skips initialization if error state is active (not expired)", async () => {
      (getIsDebug as unknown as Mock).mockReturnValue(false);
      const mockConfig = {
        get: vi.fn().mockReturnValue({
          environmentId: "env_123",
          appUrl: "https://my.url",
          environment: {},
          user: { data: {}, expiresAt: null },
          status: { value: "error", expiresAt: new Date(Date.now() + 10000) },
        }),
        resetConfig: vi.fn(),
      };

      getInstanceConfigMock.mockReturnValue(mockConfig as unknown as Config);
      (isNowExpired as unknown as Mock).mockReturnValue(false); // Time is NOT up

      const result = await setup({ environmentId: "env_123", appUrl: "https://my.url" });

      expect(result.ok).toBe(true);
      // Should NOT fetch environment or user state
      expect(fetchEnvironmentState).not.toHaveBeenCalled();
      expect(mockConfig.resetConfig).not.toHaveBeenCalled();
    });

    test("continues initialization if error state is expired", async () => {
      (getIsDebug as unknown as Mock).mockReturnValue(false);
      const mockConfig = {
        get: vi.fn().mockReturnValue({
          environmentId: "env_123",
          appUrl: "https://my.url",
          environment: { data: { surveys: [] }, expiresAt: new Date() },
          user: { data: {}, expiresAt: null },
          status: { value: "error", expiresAt: new Date(Date.now() - 10000) },
        }),
        update: vi.fn(),
      };

      getInstanceConfigMock.mockReturnValue(mockConfig as unknown as Config);
      (isNowExpired as unknown as Mock).mockReturnValue(true); // Time IS up

      // Mock successful fetch to allow setup to proceed
      (fetchEnvironmentState as unknown as Mock).mockResolvedValueOnce({
        ok: true,
        data: { data: { surveys: [] }, expiresAt: new Date() },
      });
      (filterSurveys as unknown as Mock).mockReturnValue([]);

      const result = await setup({ environmentId: "env_123", appUrl: "https://my.url" });

      expect(result.ok).toBe(true);
      expect(fetchEnvironmentState).toHaveBeenCalled();
    });

    test("uses existing config if environmentId/appUrl match, checks for expiration sync", async () => {
      const mockConfig = {
        get: vi.fn().mockReturnValue({
          environmentId: "env_123",
          appUrl: "https://my.url",
          environment: { expiresAt: new Date(Date.now() - 5000), data: { actionClasses: [] } }, // environment expired
          user: {
            data: { userId: "user_abc" },
            expiresAt: new Date(Date.now() - 5000), // also expired
          },
          status: { value: "success", expiresAt: null },
        }),
        update: vi.fn(),
      };

      getInstanceConfigMock.mockReturnValue(mockConfig as unknown as Config);

      (isNowExpired as unknown as Mock).mockReturnValue(true);

      // Mock environment fetch success
      (fetchEnvironmentState as unknown as Mock).mockResolvedValueOnce({
        ok: true,
        data: { data: { surveys: [] }, expiresAt: new Date(Date.now() + 60_000) },
      });

      // Mock sendUpdatesToBackend success
      (sendUpdatesToBackend as unknown as Mock).mockResolvedValueOnce({
        ok: true,
        data: {
          state: {
            expiresAt: new Date(),
            data: { userId: "user_abc", segments: [] },
          },
        },
      });

      (filterSurveys as unknown as Mock).mockReturnValueOnce([{ name: "S1" }, { name: "S2" }]);

      const result = await setup({ environmentId: "env_123", appUrl: "https://my.url" });
      expect(result.ok).toBe(true);

      // environmentState was fetched
      expect(fetchEnvironmentState).toHaveBeenCalled();
      // user state was updated
      expect(sendUpdatesToBackend).toHaveBeenCalled();
      // filterSurveys called
      expect(filterSurveys).toHaveBeenCalled();
      // config updated
      expect(mockConfig.update).toHaveBeenCalledWith(
        expect.objectContaining({
          // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment -- required for testing this object
          user: expect.objectContaining({
            data: { userId: "user_abc", segments: [] },
          }),
          filteredSurveys: [{ name: "S1" }, { name: "S2" }],
        })
      );
    });

    test("resets config if no valid config found, fetches environment, sets default user", async () => {
      const mockConfig = {
        get: () => {
          throw new Error("no config found");
        },
        resetConfig: vi.fn(),
        update: vi.fn(),
      };

      getInstanceConfigMock.mockReturnValue(mockConfig as unknown as Config);

      (fetchEnvironmentState as unknown as Mock).mockResolvedValueOnce({
        ok: true,
        data: {
          data: {
            surveys: [{ name: "SurveyA" }],
            expiresAt: new Date(Date.now() + 60000),
          },
        },
      });

      (filterSurveys as unknown as Mock).mockReturnValueOnce([{ name: "SurveyA" }]);

      const result = await setup({ environmentId: "envX", appUrl: "https://urlX" });
      expect(result.ok).toBe(true);
      expect(mockLogger.debug).toHaveBeenCalledWith("No existing configuration found.");
      expect(mockLogger.debug).toHaveBeenCalledWith(
        "No valid configuration found. Resetting config and creating new one."
      );
      expect(mockConfig.resetConfig).toHaveBeenCalled();
      expect(fetchEnvironmentState).toHaveBeenCalled();
      expect(mockConfig.update).toHaveBeenCalledWith({
        appUrl: "https://urlX",
        environmentId: "envX",
        user: DEFAULT_USER_STATE_NO_USER_ID,
        environment: {
          data: {
            surveys: [{ name: "SurveyA" }],
            // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment -- mock
            expiresAt: expect.any(Date),
          },
        },
        filteredSurveys: [{ name: "SurveyA" }],
      });
    });

    test("calls handleErrorOnFirstSetup if environment fetch fails initially", async () => {
      const mockConfig = {
        get: vi.fn().mockReturnValue(undefined),
        update: vi.fn(),
        resetConfig: vi.fn(),
      };

      getInstanceConfigMock.mockReturnValueOnce(mockConfig as unknown as Config);

      (fetchEnvironmentState as unknown as Mock).mockResolvedValueOnce({
        ok: false,
        error: { code: "forbidden", responseMessage: "No access" },
      });

      await expect(setup({ environmentId: "envX", appUrl: "https://urlX" })).rejects.toThrow(
        "Could not set up formbricks"
      );
    });

    test("adds event listeners and sets isSetup", async () => {
      const mockConfig = {
        get: vi.fn().mockReturnValue({
          environmentId: "env_abc",
          appUrl: "https://test.app",
          environment: { expiresAt: new Date(Date.now() - 5000), data: { actionClasses: [] } }, // environment expired
          user: { data: {}, expiresAt: null },
          status: { value: "success", expiresAt: null },
        }),
        update: vi.fn(),
      };

      getInstanceConfigMock.mockReturnValue(mockConfig as unknown as Config);

      const result = await setup({ environmentId: "env_abc", appUrl: "https://test.app" });
      expect(result.ok).toBe(true);
      expect(addEventListeners).toHaveBeenCalled();
      expect(addCleanupEventListeners).toHaveBeenCalled();
    });
  });

  describe("tearDown()", () => {
    test("resets user state to default", () => {
      const mockConfig = {
        get: vi.fn().mockReturnValue({
          environment: { data: { surveys: [] } },
          user: { data: { userId: "XYZ" } },
        }),
        update: vi.fn(),
      };

      getInstanceConfigMock.mockReturnValue(mockConfig as unknown as Config);

      tearDown();

      expect(mockConfig.update).toHaveBeenCalledWith(
        expect.objectContaining({
          user: DEFAULT_USER_STATE_NO_USER_ID,
        })
      );
      expect(filterSurveys).toHaveBeenCalled();
    });
  });

  describe("handleErrorOnFirstSetup()", () => {
    test("stores error state in AsyncStorage, throws error", async () => {
      // We import the function directly
      const errorObj = { code: "forbidden", responseMessage: "No access" };

      await expect(async () => {
        await handleErrorOnFirstSetup(errorObj);
      }).rejects.toThrow("Could not set up formbricks");

      expect(setItemMock).toHaveBeenCalledWith(
        JS_LOCAL_STORAGE_KEY,
        expect.stringContaining('"value":"error"')
      );
    });

    test("logs generic error for non-forbidden code", async () => {
      const errorObj = { code: "server_error", responseMessage: "Internal error" };

      await expect(async () => {
        await handleErrorOnFirstSetup(errorObj);
      }).rejects.toThrow("Could not set up formbricks");

      expect(mockLogger.error).toHaveBeenCalledWith(expect.stringContaining("Error during first setup"));
    });
  });

  describe("putFormbricksInErrorState()", () => {
    test("sets config status to error and calls tearDown", () => {
      (getIsDebug as Mock).mockReturnValue(false);

      const mockConfig = {
        get: vi.fn().mockReturnValue({
          environment: { data: { surveys: [] } },
          user: DEFAULT_USER_STATE_NO_USER_ID,
          status: { value: "success", expiresAt: null },
        }),
        update: vi.fn(),
      };

      getInstanceConfigMock.mockReturnValue(mockConfig as unknown as Config);

      putFormbricksInErrorState(mockConfig as unknown as Config);

      expect(mockConfig.update).toHaveBeenCalledWith(
        expect.objectContaining({
          status: expect.objectContaining({ value: "error" }),
        })
      );
    });

    test("skips error state in debug mode", () => {
      (getIsDebug as Mock).mockReturnValue(true);

      const mockConfig = {
        get: vi.fn(),
        update: vi.fn(),
      };

      putFormbricksInErrorState(mockConfig as unknown as Config);

      expect(mockConfig.update).not.toHaveBeenCalled();
    });
  });

  describe("setup() with embed modes", () => {
    // Store created elements so we can look them up by id
    let createdElements: Record<string, Record<string, unknown>> = {};

    beforeEach(() => {
      // Clear our tracking map
      createdElements = {};

      // Override document.createElement to return objects that support
      // the DOM methods used by the embed init functions
      (document.createElement as Mock).mockImplementation(() => {
        const listeners: Record<string, (() => void)[]> = {};
        const styleObj: Record<string, string> = {};
        const el: Record<string, unknown> = {
          setAttribute: vi.fn(),
          style: styleObj,
          addEventListener: vi.fn((event: string, cb: () => void) => {
            if (!listeners[event]) listeners[event] = [];
            listeners[event].push(cb);
          }),
          click: vi.fn(() => {
            const clickHandlers = listeners.click;
            if (clickHandlers) {
              for (const cb of clickHandlers) cb();
            }
          }),
          set id(val: string) {
            el._id = val;
            createdElements[val] = el;
          },
          get id() {
            return el._id as string;
          },
          set textContent(val: string) {
            el._textContent = val;
          },
          get textContent() {
            return el._textContent as string;
          },
        };
        return el;
      });

      // Override getElementById to look up our created elements
      (document.getElementById as Mock).mockImplementation((id: string) => {
        return createdElements[id] ?? null;
      });
    });

    test("setup with slider embedMode creates slider container", async () => {
      setIsSetup(false);
      (getIsDebug as Mock).mockReturnValue(false);
      (isNowExpired as Mock).mockReturnValue(false);

      const mockConfig = {
        get: vi.fn().mockReturnValue({
          environmentId: "env_slider",
          appUrl: "https://test.app",
          environment: {
            data: { surveys: [] },
            expiresAt: new Date(Date.now() + 60000).toISOString(),
          },
          user: DEFAULT_USER_STATE_NO_USER_ID,
          status: { value: "success", expiresAt: null },
          filteredSurveys: [],
        }),
        update: vi.fn(),
        resetConfig: vi.fn(),
      };

      getInstanceConfigMock.mockReturnValue(mockConfig as unknown as Config);
      (filterSurveys as Mock).mockReturnValue([]);

      const result = await setup({
        environmentId: "env_slider",
        appUrl: "https://test.app",
        embedMode: "slider",
        sliderConfig: { direction: "right", width: "400px", animation: 300 },
      });

      expect(result.ok).toBe(true);
      expect(mockLogger.debug).toHaveBeenCalledWith("Slider embed container created");
      expect(document.body.appendChild).toHaveBeenCalled();
    });

    test("setup with popover embedMode creates popover container and button", async () => {
      setIsSetup(false);
      (getIsDebug as Mock).mockReturnValue(false);
      (isNowExpired as Mock).mockReturnValue(false);

      const mockConfig = {
        get: vi.fn().mockReturnValue({
          environmentId: "env_popover",
          appUrl: "https://test.app",
          environment: {
            data: { surveys: [] },
            expiresAt: new Date(Date.now() + 60000).toISOString(),
          },
          user: DEFAULT_USER_STATE_NO_USER_ID,
          status: { value: "success", expiresAt: null },
          filteredSurveys: [],
        }),
        update: vi.fn(),
        resetConfig: vi.fn(),
      };

      getInstanceConfigMock.mockReturnValue(mockConfig as unknown as Config);
      (filterSurveys as Mock).mockReturnValue([]);

      const result = await setup({
        environmentId: "env_popover",
        appUrl: "https://test.app",
        embedMode: "popover",
        popoverConfig: {
          buttonPosition: "bottom-right",
          color: "#FF0000",
          formWidth: "400px",
          formHeight: "500px",
        },
      });

      expect(result.ok).toBe(true);
      expect(mockLogger.debug).toHaveBeenCalledWith("Popover embed container created");
      // Two elements appended: button + form container
      expect(document.body.appendChild).toHaveBeenCalledTimes(2);
    });

    test("setup with sideTab embedMode creates side tab container and button", async () => {
      setIsSetup(false);
      (getIsDebug as Mock).mockReturnValue(false);
      (isNowExpired as Mock).mockReturnValue(false);

      const mockConfig = {
        get: vi.fn().mockReturnValue({
          environmentId: "env_sidetab",
          appUrl: "https://test.app",
          environment: {
            data: { surveys: [] },
            expiresAt: new Date(Date.now() + 60000).toISOString(),
          },
          user: DEFAULT_USER_STATE_NO_USER_ID,
          status: { value: "success", expiresAt: null },
          filteredSurveys: [],
        }),
        update: vi.fn(),
        resetConfig: vi.fn(),
      };

      getInstanceConfigMock.mockReturnValue(mockConfig as unknown as Config);
      (filterSurveys as Mock).mockReturnValue([]);

      const result = await setup({
        environmentId: "env_sidetab",
        appUrl: "https://test.app",
        embedMode: "sideTab",
        sideTabConfig: { tabLabel: "Feedback", position: "right", color: "#00C4B8" },
      });

      expect(result.ok).toBe(true);
      expect(mockLogger.debug).toHaveBeenCalledWith("Side tab embed container created");
      // Two elements appended: tab button + container
      expect(document.body.appendChild).toHaveBeenCalledTimes(2);
    });

    test("popover button click toggles form container visibility", async () => {
      setIsSetup(false);
      (getIsDebug as Mock).mockReturnValue(false);
      (isNowExpired as Mock).mockReturnValue(false);

      const mockConfig = {
        get: vi.fn().mockReturnValue({
          environmentId: "env_popover_toggle",
          appUrl: "https://test.app",
          environment: {
            data: { surveys: [] },
            expiresAt: new Date(Date.now() + 60000).toISOString(),
          },
          user: DEFAULT_USER_STATE_NO_USER_ID,
          status: { value: "success", expiresAt: null },
          filteredSurveys: [],
        }),
        update: vi.fn(),
        resetConfig: vi.fn(),
      };

      getInstanceConfigMock.mockReturnValue(mockConfig as unknown as Config);
      (filterSurveys as Mock).mockReturnValue([]);

      await setup({
        environmentId: "env_popover_toggle",
        appUrl: "https://test.app",
        embedMode: "popover",
        popoverConfig: { buttonPosition: "bottom-left" },
      });

      const popoverBtn = createdElements["formbricks-popover-button"];
      const formContainer = createdElements["formbricks-popover-container"];

      expect(formContainer).toBeDefined();
      expect((formContainer.style as Record<string, string>).display).toBe("none");
      // Trigger click via stored listener
      (popoverBtn.click as Mock)();
      expect((formContainer.style as Record<string, string>).display).toBe("block");
      (popoverBtn.click as Mock)();
      expect((formContainer.style as Record<string, string>).display).toBe("none");
    });

    test("side tab button click toggles container visibility", async () => {
      setIsSetup(false);
      (getIsDebug as Mock).mockReturnValue(false);
      (isNowExpired as Mock).mockReturnValue(false);

      const mockConfig = {
        get: vi.fn().mockReturnValue({
          environmentId: "env_sidetab_toggle",
          appUrl: "https://test.app",
          environment: {
            data: { surveys: [] },
            expiresAt: new Date(Date.now() + 60000).toISOString(),
          },
          user: DEFAULT_USER_STATE_NO_USER_ID,
          status: { value: "success", expiresAt: null },
          filteredSurveys: [],
        }),
        update: vi.fn(),
        resetConfig: vi.fn(),
      };

      getInstanceConfigMock.mockReturnValue(mockConfig as unknown as Config);
      (filterSurveys as Mock).mockReturnValue([]);

      await setup({
        environmentId: "env_sidetab_toggle",
        appUrl: "https://test.app",
        embedMode: "sideTab",
        sideTabConfig: { tabLabel: "Help", position: "left", color: "#333" },
      });

      const tabBtn = createdElements["formbricks-side-tab-button"];
      const container = createdElements["formbricks-side-tab-container"];

      expect(container).toBeDefined();
      expect((container.style as Record<string, string>).display).toBe("none");
      (tabBtn.click as Mock)();
      expect((container.style as Record<string, string>).display).toBe("block");
      (tabBtn.click as Mock)();
      expect((container.style as Record<string, string>).display).toBe("none");
    });

    test("slider left direction creates container with left position", async () => {
      setIsSetup(false);
      (getIsDebug as Mock).mockReturnValue(false);
      (isNowExpired as Mock).mockReturnValue(false);

      const mockConfig = {
        get: vi.fn().mockReturnValue({
          environmentId: "env_slider_left",
          appUrl: "https://test.app",
          environment: {
            data: { surveys: [] },
            expiresAt: new Date(Date.now() + 60000).toISOString(),
          },
          user: DEFAULT_USER_STATE_NO_USER_ID,
          status: { value: "success", expiresAt: null },
          filteredSurveys: [],
        }),
        update: vi.fn(),
        resetConfig: vi.fn(),
      };

      getInstanceConfigMock.mockReturnValue(mockConfig as unknown as Config);
      (filterSurveys as Mock).mockReturnValue([]);

      const result = await setup({
        environmentId: "env_slider_left",
        appUrl: "https://test.app",
        embedMode: "slider",
        sliderConfig: { direction: "left" },
      });

      expect(result.ok).toBe(true);
      const sliderEl = createdElements["formbricks-slider-container"];
      expect(sliderEl).toBeDefined();
      expect((sliderEl.style as Record<string, string>).left).toBe("0");
      expect((sliderEl.style as Record<string, string>).transform).toBe("translateX(-100%)");
    });

    test("setup with unknown embedMode logs debug message", async () => {
      setIsSetup(false);
      (getIsDebug as Mock).mockReturnValue(false);
      (isNowExpired as Mock).mockReturnValue(false);

      const mockConfig = {
        get: vi.fn().mockReturnValue({
          environmentId: "env_unknown",
          appUrl: "https://test.app",
          environment: {
            data: { surveys: [] },
            expiresAt: new Date(Date.now() + 60000).toISOString(),
          },
          user: DEFAULT_USER_STATE_NO_USER_ID,
          status: { value: "success", expiresAt: null },
          filteredSurveys: [],
        }),
        update: vi.fn(),
        resetConfig: vi.fn(),
      };

      getInstanceConfigMock.mockReturnValue(mockConfig as unknown as Config);
      (filterSurveys as Mock).mockReturnValue([]);

      const result = await setup({
        environmentId: "env_unknown",
        appUrl: "https://test.app",
        embedMode: "unknown" as "slider",
      });

      expect(result.ok).toBe(true);
      expect(mockLogger.debug).toHaveBeenCalledWith(expect.stringContaining("Unknown embed mode"));
    });
  });
});
