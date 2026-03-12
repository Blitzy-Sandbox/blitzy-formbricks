// @vitest-environment happy-dom
import { describe, expect, test, vi } from "vitest";
import { type TJsEnvironmentStateSurvey } from "@formbricks/types/js";
import { type TResponseData, type TResponseVariables } from "@formbricks/types/responses";
import { type TSurveyBlockLogicAction } from "@formbricks/types/surveys/blocks";
import { TSurveyElementTypeEnum } from "@formbricks/types/surveys/constants";
import { type TConditionGroup, type TSingleCondition } from "@formbricks/types/surveys/logic";
import { type TSurveyVariable } from "@formbricks/types/surveys/types";
import { evaluateLogic, isConditionGroup, performActions } from "./logic";

// Mock the imported function
vi.mock("@/lib/i18n", () => ({
  getLocalizedValue: vi.fn((value, language) => {
    if (typeof value === "object") {
      return value[language] || value["default"] || "";
    }
    return value;
  }),
}));

describe("Survey Logic", () => {
  // Mock data for reuse across tests
  const mockVariables: TSurveyVariable[] = [
    { id: "var1", name: "Variable 1", type: "text", value: "string value" },
    { id: "var2", name: "Variable 2", type: "number", value: 50 },
    { id: "var3", name: "Variable 3", type: "text", value: "another string" },
  ];

  const mockSurvey: TJsEnvironmentStateSurvey = {
    id: "survey1",
    name: "Test Survey",
    questions: [], // Deprecated - using blocks instead
    blocks: [
      {
        id: "block1",
        name: "Block 1",
        elements: [
          {
            id: "q1",
            type: TSurveyElementTypeEnum.OpenText,
            headline: { default: "Question 1" },
            subheader: { default: "Enter some text" },
            required: true,
            inputType: "text",
            charLimit: { enabled: false },
          },
          {
            id: "q2",
            type: TSurveyElementTypeEnum.OpenText,
            headline: { default: "Question 2" },
            subheader: { default: "Enter a number" },
            required: true,
            inputType: "number",
            charLimit: { enabled: false },
          },
          {
            id: "q3",
            type: TSurveyElementTypeEnum.MultipleChoiceSingle,
            headline: { default: "Question 3" },
            subheader: { default: "Select one option" },
            required: true,
            choices: [
              { id: "opt1", label: { default: "Option 1", es: "Opción 1" } },
              { id: "opt2", label: { default: "Option 2", es: "Opción 2" } },
              { id: "other", label: { default: "Other", es: "Otro" } },
            ],
          },
          {
            id: "q4",
            type: TSurveyElementTypeEnum.MultipleChoiceMulti,
            headline: { default: "Question 4" },
            subheader: { default: "Select multiple options" },
            required: true,
            choices: [
              { id: "opt1", label: { default: "Option 1", es: "Opción 1" } },
              { id: "opt2", label: { default: "Option 2", es: "Opción 2" } },
              { id: "opt3", label: { default: "Option 3", es: "Opción 3" } },
            ],
          },
          {
            id: "q5",
            type: TSurveyElementTypeEnum.Date,
            headline: { default: "Question 5" },
            subheader: { default: "Select a date" },
            required: true,
            format: "d-M-y",
          },
          {
            id: "q6",
            type: TSurveyElementTypeEnum.FileUpload,
            headline: { default: "Question 6" },
            subheader: { default: "Upload a file" },
            required: true,
            allowMultipleFiles: true,
          },
          {
            id: "q7",
            type: TSurveyElementTypeEnum.PictureSelection,
            headline: { default: "Question 7" },
            subheader: { default: "Select pictures" },
            required: true,
            allowMulti: true,
            choices: [
              { id: "pic1", imageUrl: "url1" },
              { id: "pic2", imageUrl: "url2" },
            ],
          },
          {
            id: "q8",
            type: TSurveyElementTypeEnum.Matrix,
            headline: { default: "Question 8" },
            subheader: { default: "Matrix question" },
            required: true,
            rows: [
              { id: "row1", label: { default: "Row 1", es: "Fila 1" } },
              { id: "row2", label: { default: "Row 2", es: "Fila 2" } },
            ],
            columns: [
              { id: "col1", label: { default: "Column 1", es: "Columna 1" } },
              { id: "col2", label: { default: "Column 2", es: "Columna 2" } },
            ],
            shuffleOption: "none",
          },
          {
            id: "qOpinionScale",
            type: TSurveyElementTypeEnum.OpinionScale,
            headline: { default: "How would you rate this?" },
            subheader: { default: "Select a value" },
            required: true,
            scaleRange: 5,
            lowerLabel: { default: "Not at all" },
            upperLabel: { default: "Very much" },
            visualStyle: "number",
            isColorCodingEnabled: false,
          },
          {
            id: "qPayment",
            type: TSurveyElementTypeEnum.Payment,
            headline: { default: "Complete your payment" },
            subheader: { default: "Enter card details" },
            required: true,
            currency: "usd",
            amount: 1000,
            buttonLabel: { default: "Pay $10.00" },
            stripeIntegration: {
              publicKey: "pk_test_abc123",
            },
          },
        ],
      },
    ],
    variables: mockVariables,
    hiddenFields: {
      enabled: true,
      fieldIds: ["fieldId1"],
    },
    autoClose: null,
    type: "link",
    delay: 0,
    displayLimit: 0,
    displayOption: "displayMultiple",
    displayPercentage: 0,
    recaptcha: { enabled: false, threshold: 0.5 },
    isBackButtonHidden: false,
    segment: null,
    welcomeCard: {
      enabled: true,
      showResponseCount: true,
      timeToFinish: true,
    },
    triggers: [],
    styling: null,
    status: "inProgress",
    showLanguageSwitch: false,
    languages: [],
    endings: [],
    projectOverwrites: null,
    recontactDays: null,
  };

  describe("isConditionGroup", () => {
    test("returns true for condition groups", () => {
      const conditionGroup: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [],
      };
      expect(isConditionGroup(conditionGroup)).toBe(true);
    });

    test("returns false for single conditions", () => {
      const singleCondition: TSingleCondition = {
        id: "condition1",
        operator: "equals",
        leftOperand: { type: "element", value: "q1" },
        rightOperand: { type: "static", value: "test" },
      };
      expect(isConditionGroup(singleCondition)).toBe(false);
    });
  });

  describe("evaluateLogic", () => {
    const mockData: TResponseData = {
      q1: "test answer",
      q2: 42,
      q3: "Option 1",
      q4: ["Option 1", "Option 2"],
      q5: "2023-01-01",
      q7: ["pic1", "pic2"],
      q8: { "Row 1": "Column 1", "Row 2": "Column 2" },
      fieldId1: "hidden value",
    };

    const mockVariablesData: TResponseVariables = {
      var1: "string value",
      var2: 123,
      var3: "another string",
    };

    test("evaluates a simple condition group with AND connector", () => {
      const conditions: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "equals",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "static", value: "test answer" },
          },
          {
            id: "condition2",
            operator: "equals",
            leftOperand: { type: "element", value: "q2" },
            rightOperand: { type: "static", value: 42 },
          },
        ],
      };

      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, conditions, "default")).toBe(true);
    });

    test("evaluates a simple condition group with OR connector", () => {
      const conditions: TConditionGroup = {
        id: "group1",
        connector: "or",
        conditions: [
          {
            id: "condition1",
            operator: "equals",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "static", value: "wrong answer" },
          },
          {
            id: "condition2",
            operator: "equals",
            leftOperand: { type: "element", value: "q2" },
            rightOperand: { type: "static", value: 42 },
          },
        ],
      };

      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, conditions, "default")).toBe(true);
    });

    test("evaluates a nested condition group", () => {
      const conditions: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "equals",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "static", value: "test answer" },
          },
          {
            id: "group2",
            connector: "or",
            conditions: [
              {
                id: "condition2",
                operator: "equals",
                leftOperand: { type: "element", value: "q2" },
                rightOperand: { type: "static", value: "wrong" },
              },
              {
                id: "condition3",
                operator: "equals",
                leftOperand: { type: "variable", value: "var1" },
                rightOperand: { type: "static", value: "string value" },
              },
            ],
          },
        ],
      };

      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, conditions, "default")).toBe(true);
    });

    test("evaluates false when any condition fails in AND group", () => {
      const conditions: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "equals",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "static", value: "test answer" },
          },
          {
            id: "condition2",
            operator: "equals",
            leftOperand: { type: "element", value: "q2" },
            rightOperand: { type: "static", value: "wrong value" },
          },
        ],
      };

      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, conditions, "default")).toBe(false);
    });

    test("evaluates false when all conditions fail in OR group", () => {
      const conditions: TConditionGroup = {
        id: "group1",
        connector: "or",
        conditions: [
          {
            id: "condition1",
            operator: "equals",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "static", value: "wrong answer" },
          },
          {
            id: "condition2",
            operator: "equals",
            leftOperand: { type: "element", value: "q2" },
            rightOperand: { type: "static", value: "wrong value" },
          },
        ],
      };

      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, conditions, "default")).toBe(false);
    });

    test("evaluates conditions with variable as left operand", () => {
      const conditions: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "equals",
            leftOperand: { type: "variable", value: "var1" },
            rightOperand: { type: "static", value: "string value" },
          },
        ],
      };

      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, conditions, "default")).toBe(true);
    });

    test("evaluates conditions with hidden field as left operand", () => {
      const conditions: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "equals",
            leftOperand: { type: "hiddenField", value: "fieldId1" },
            rightOperand: { type: "static", value: "hidden value" },
          },
        ],
      };

      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, conditions, "default")).toBe(true);
    });
  });

  describe("performActions", () => {
    const mockData: TResponseData = {
      q1: "test answer",
      q2: "42",
      q3: "opt1",
    };

    const mockVariablesData: TResponseVariables = {
      var1: "string value",
      var2: 50,
      var3: "",
    };

    test("performs jump action", () => {
      const actions: TSurveyBlockLogicAction[] = [
        {
          id: "var1",
          objective: "jumpToBlock",
          target: "q5",
        },
      ];

      const result = performActions(mockSurvey, actions, mockData, mockVariablesData);
      expect(result.jumpTarget).toBe("q5");
      expect(result.requiredQuestionIds).toEqual([]);
      expect(result.calculations).toEqual(mockVariablesData);
    });

    test("performs require answer action", () => {
      const actions: TSurveyBlockLogicAction[] = [
        {
          id: "var1",
          objective: "requireAnswer",
          target: "q4",
        },
      ];

      const result = performActions(mockSurvey, actions, mockData, mockVariablesData);
      expect(result.jumpTarget).toBeUndefined();
      expect(result.requiredQuestionIds).toEqual(["q4"]);
      expect(result.calculations).toEqual(mockVariablesData);
    });

    test("performs calculate action - add", () => {
      const actions: TSurveyBlockLogicAction[] = [
        {
          id: "var2",
          objective: "calculate",
          variableId: "var2",
          operator: "add",
          value: { type: "static", value: 10 },
        },
      ];

      const result = performActions(mockSurvey, actions, mockData, mockVariablesData);
      expect(result.calculations.var2).toBe(60);
    });

    test("performs calculate action - subtract", () => {
      const actions: TSurveyBlockLogicAction[] = [
        {
          id: "var2",
          objective: "calculate",
          variableId: "var2",
          operator: "subtract",
          value: { type: "static", value: 10 },
        },
      ];

      const result = performActions(mockSurvey, actions, mockData, mockVariablesData);
      expect(result.calculations.var2).toBe(40);
    });

    test("performs calculate action - multiply", () => {
      const actions: TSurveyBlockLogicAction[] = [
        {
          id: "var2",
          objective: "calculate",
          variableId: "var2",
          operator: "multiply",
          value: { type: "static", value: 2 },
        },
      ];

      const result = performActions(mockSurvey, actions, mockData, mockVariablesData);
      expect(result.calculations.var2).toBe(100);
    });

    test("performs calculate action - divide", () => {
      const actions: TSurveyBlockLogicAction[] = [
        {
          id: "var2",
          objective: "calculate",
          variableId: "var2",
          operator: "divide",
          value: { type: "static", value: 2 },
        },
      ];

      const result = performActions(mockSurvey, actions, mockData, mockVariablesData);
      expect(result.calculations.var2).toBe(25);
    });

    test("handles divide by zero", () => {
      const actions: TSurveyBlockLogicAction[] = [
        {
          id: "var2",
          objective: "calculate",
          variableId: "var2",
          operator: "divide",
          value: { type: "static", value: 0 },
        },
      ];

      const result = performActions(mockSurvey, actions, mockData, mockVariablesData);
      expect(result.calculations.var2).toBe(50); // Original value preserved
    });

    test("performs calculate action - assign", () => {
      const actions: TSurveyBlockLogicAction[] = [
        {
          id: "var2",
          objective: "calculate",
          variableId: "var2",
          operator: "assign",
          value: { type: "static", value: 200 },
        },
      ];

      const result = performActions(mockSurvey, actions, mockData, mockVariablesData);
      expect(result.calculations.var2).toBe(200);
    });

    test("performs calculate action - concat", () => {
      const actions: TSurveyBlockLogicAction[] = [
        {
          id: "var1",
          objective: "calculate",
          variableId: "var1",
          operator: "concat",
          value: { type: "static", value: " appended" },
        },
      ];

      const result = performActions(mockSurvey, actions, mockData, mockVariablesData);
      expect(result.calculations.var1).toBe("string value appended");
    });

    test("performs calculate action with question value", () => {
      const actions: TSurveyBlockLogicAction[] = [
        {
          id: "var2",
          objective: "calculate",
          variableId: "var2",
          operator: "add",
          value: { type: "element", value: "q2" },
        },
      ];

      const result = performActions(mockSurvey, actions, mockData, mockVariablesData);
      expect(result.calculations.var2).toBe(92); // 50 + 42
    });

    test("performs calculate action with variable value", () => {
      const actions: TSurveyBlockLogicAction[] = [
        {
          id: "var2",
          objective: "calculate",
          variableId: "var2",
          operator: "add",
          value: { type: "variable", value: "var2" },
        },
      ];

      const result = performActions(mockSurvey, actions, mockData, mockVariablesData);
      expect(result.calculations.var2).toBe(100); // 50 + 50
    });

    test("performs multiple actions in order", () => {
      const actions: TSurveyBlockLogicAction[] = [
        {
          id: "var2",
          objective: "calculate",
          variableId: "var2",
          operator: "add",
          value: { type: "static", value: 10 },
        },
        {
          id: "var2",
          objective: "requireAnswer",
          target: "q4",
        },
        {
          id: "var2",
          objective: "jumpToBlock",
          target: "q5",
        },
      ];

      const result = performActions(mockSurvey, actions, mockData, mockVariablesData);
      expect(result.jumpTarget).toBe("q5");
      expect(result.requiredQuestionIds).toEqual(["q4"]);
      expect(result.calculations.var2).toBe(60);
    });

    test("takes first jump target when multiple jump actions exist", () => {
      const actions: TSurveyBlockLogicAction[] = [
        {
          id: "var2",
          objective: "jumpToBlock",
          target: "q2",
        },
        {
          id: "var2",
          objective: "jumpToBlock",
          target: "q3",
        },
      ];

      const result = performActions(mockSurvey, actions, mockData, mockVariablesData);
      expect(result.jumpTarget).toBe("q2");
    });
  });

  // Additional tests for complex condition evaluations
  describe("Condition Evaluations", () => {
    // Test data for different question types and operators
    const mockData: TResponseData = {
      q1: "test answer",
      q2: "42",
      q3: "Option 1", // MultipleChoiceSingle
      q4: ["Option 1", "Option 2"], // MultipleChoiceMulti
      q5: "2023-01-01", // Date
      q6: "file-url.pdf", // FileUpload
      q7: ["pic1", "pic2"], // PictureSelection
      q8: { "Row 1": "Column 1", "Row 2": "Column 2" }, // Matrix
      fieldId1: "hidden value",
      emptyField: "",
      skippedUpload: "skipped",
    };

    const mockVariablesData: TResponseVariables = {
      var1: "string value",
      var2: 123,
      var3: "2023-05-05",
    };

    test("evaluates string comparison operators", () => {
      // Tests for contains, startsWith, endsWith and their negations
      const containsCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "contains",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "static", value: "test" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, containsCondition, "default")).toBe(true);

      const doesNotContainCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "doesNotContain",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "static", value: "invalid" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, doesNotContainCondition, "default")).toBe(
        true
      );

      const startsWithCondition: TConditionGroup = {
        id: "group3",
        connector: "and",
        conditions: [
          {
            id: "condition3",
            operator: "startsWith",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "static", value: "test" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, startsWithCondition, "default")).toBe(
        true
      );

      const doesNotStartWithCondition: TConditionGroup = {
        id: "group4",
        connector: "and",
        conditions: [
          {
            id: "condition4",
            operator: "doesNotStartWith",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "static", value: "invalid" },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, mockData, mockVariablesData, doesNotStartWithCondition, "default")
      ).toBe(true);

      const endsWithCondition: TConditionGroup = {
        id: "group5",
        connector: "and",
        conditions: [
          {
            id: "condition5",
            operator: "endsWith",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "static", value: "answer" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, endsWithCondition, "default")).toBe(true);

      const doesNotEndWithCondition: TConditionGroup = {
        id: "group6",
        connector: "and",
        conditions: [
          {
            id: "condition6",
            operator: "doesNotEndWith",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "static", value: "invalid" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, doesNotEndWithCondition, "default")).toBe(
        true
      );
    });

    test("evaluates number comparison operators", () => {
      // Tests for isGreaterThan, isLessThan, etc.
      const greaterThanCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "isGreaterThan",
            leftOperand: { type: "element", value: "q2" },
            rightOperand: { type: "static", value: "30" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, greaterThanCondition, "default")).toBe(
        true
      );

      const lessThanCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "isLessThan",
            leftOperand: { type: "element", value: "q2" },
            rightOperand: { type: "static", value: "50" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, lessThanCondition, "default")).toBe(true);

      const greaterThanOrEqualCondition: TConditionGroup = {
        id: "group3",
        connector: "and",
        conditions: [
          {
            id: "condition3",
            operator: "isGreaterThanOrEqual",
            leftOperand: { type: "element", value: "q2" },
            rightOperand: { type: "static", value: "42" },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, mockData, mockVariablesData, greaterThanOrEqualCondition, "default")
      ).toBe(true);

      const lessThanOrEqualCondition: TConditionGroup = {
        id: "group4",
        connector: "and",
        conditions: [
          {
            id: "condition4",
            operator: "isLessThanOrEqual",
            leftOperand: { type: "element", value: "q2" },
            rightOperand: { type: "static", value: "42" },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, mockData, mockVariablesData, lessThanOrEqualCondition, "default")
      ).toBe(true);
    });

    test("evaluates date comparison operators", () => {
      // Tests for isAfter, isBefore
      const afterCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "isAfter",
            leftOperand: { type: "element", value: "q5" },
            rightOperand: { type: "static", value: "2022-12-31" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, afterCondition, "default")).toBe(true);

      const beforeCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "isBefore",
            leftOperand: { type: "element", value: "q5" },
            rightOperand: { type: "static", value: "2023-01-02" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, beforeCondition, "default")).toBe(true);

      const dateEqualCondition: TConditionGroup = {
        id: "group3",
        connector: "and",
        conditions: [
          {
            id: "condition3",
            operator: "equals",
            leftOperand: { type: "element", value: "q5" },
            rightOperand: { type: "static", value: "2023-01-01" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, dateEqualCondition, "default")).toBe(
        true
      );
    });

    test("evaluates array inclusion operators", () => {
      // Tests for includesAllOf, includesOneOf, etc.
      const includesAllOfCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "includesAllOf",
            leftOperand: { type: "element", value: "q4" },
            rightOperand: { type: "static", value: ["opt1", "opt2"] },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, includesAllOfCondition, "default")).toBe(
        true
      );

      const includesOneOfCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "includesOneOf",
            leftOperand: { type: "element", value: "q4" },
            rightOperand: { type: "static", value: ["opt1", "Invalid Option"] },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, includesOneOfCondition, "default")).toBe(
        true
      );

      const doesNotIncludeAllOfCondition: TConditionGroup = {
        id: "group3",
        connector: "and",
        conditions: [
          {
            id: "condition3",
            operator: "doesNotIncludeAllOf",
            leftOperand: { type: "element", value: "q4" },
            rightOperand: { type: "static", value: ["Invalid 1", "Invalid 2"] },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, mockData, mockVariablesData, doesNotIncludeAllOfCondition, "default")
      ).toBe(true);

      const doesNotIncludeOneOfCondition: TConditionGroup = {
        id: "group4",
        connector: "and",
        conditions: [
          {
            id: "condition4",
            operator: "doesNotIncludeOneOf",
            leftOperand: { type: "element", value: "q4" },
            rightOperand: { type: "static", value: ["opt3", "Invalid Option"] },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, mockData, mockVariablesData, doesNotIncludeOneOfCondition, "default")
      ).toBe(true);
    });

    test("evaluates special state operators", () => {
      // Tests for isSubmitted, isSkipped, etc.
      const isSubmittedCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "isSubmitted",
            leftOperand: { type: "element", value: "q1" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, isSubmittedCondition, "default")).toBe(
        true
      );

      const isSkippedCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "isSkipped",
            leftOperand: { type: "element", value: "emptyField" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, isSkippedCondition, "default")).toBe(
        true
      );

      const isBookedCondition: TConditionGroup = {
        id: "group3",
        connector: "and",
        conditions: [
          {
            id: "condition3",
            operator: "isBooked",
            leftOperand: { type: "element", value: "q1" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, isBookedCondition, "default")).toBe(true);
    });

    test("evaluates isClicked and isNotClicked operators for CTA elements", () => {
      // Create a survey with a CTA element
      const ctaSurvey: TJsEnvironmentStateSurvey = {
        ...mockSurvey,
        blocks: [
          ...mockSurvey.blocks,
          {
            id: "ctaBlock",
            name: "CTA Block",
            elements: [
              {
                id: "ctaQuestion",
                type: TSurveyElementTypeEnum.CTA,
                headline: { default: "CTA Question" },
                subheader: { default: "Click the button" },
                required: false,
                buttonExternal: true,
                buttonUrl: "https://example.com",
                ctaButtonLabel: { default: "Click Me" },
              },
            ],
          },
        ],
      };

      // Test isClicked with "clicked" response
      const clickedData: TResponseData = {
        ctaQuestion: "clicked",
      };
      const isClickedCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "isClicked",
            leftOperand: { type: "element", value: "ctaQuestion" },
          },
        ],
      };
      expect(evaluateLogic(ctaSurvey, clickedData, mockVariablesData, isClickedCondition, "default")).toBe(
        true
      );

      // Test isClicked with "skipped" response (should be false)
      const skippedData: TResponseData = {
        ctaQuestion: "skipped",
      };
      expect(evaluateLogic(ctaSurvey, skippedData, mockVariablesData, isClickedCondition, "default")).toBe(
        false
      );

      // Test isNotClicked with "clicked" response (should be false)
      const isNotClickedCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "isNotClicked",
            leftOperand: { type: "element", value: "ctaQuestion" },
          },
        ],
      };
      expect(evaluateLogic(ctaSurvey, clickedData, mockVariablesData, isNotClickedCondition, "default")).toBe(
        false
      );

      // Test isNotClicked with "skipped" response (should be true)
      expect(evaluateLogic(ctaSurvey, skippedData, mockVariablesData, isNotClickedCondition, "default")).toBe(
        true
      );

      // Test isNotClicked with undefined response (should be true)
      const undefinedData: TResponseData = {};
      expect(
        evaluateLogic(ctaSurvey, undefinedData, mockVariablesData, isNotClickedCondition, "default")
      ).toBe(true);
    });

    test("evaluates matrix questions", () => {
      const matrixCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "equals",
            leftOperand: {
              type: "element",
              value: "q8",
              meta: { row: "0" },
            },
            rightOperand: { type: "static", value: "0" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, matrixCondition, "default")).toBe(true);
    });

    test("evaluates file upload questions", () => {
      const fileUploadCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "isSubmitted",
            leftOperand: { type: "element", value: "q6" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, fileUploadCondition, "default")).toBe(
        true
      );

      const skippedUploadCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "isSkipped",
            leftOperand: { type: "element", value: "skippedUpload" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, skippedUploadCondition, "default")).toBe(
        true
      );
    });

    test("evaluates partially submitted matrix question", () => {
      const partialMatrixData: TResponseData = {
        q8: { "Row 1": "Column 1", "Row 2": "" },
      };

      const partiallySubmittedCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "isPartiallySubmitted",
            leftOperand: { type: "element", value: "q8" },
          },
        ],
      };
      expect(
        evaluateLogic(
          mockSurvey,
          partialMatrixData,
          mockVariablesData,
          partiallySubmittedCondition,
          "default"
        )
      ).toBe(true);

      const completeMatrixData: TResponseData = {
        q8: { row1: "col1", row2: "col2" },
      };

      const completelySubmittedCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "isCompletelySubmitted",
            leftOperand: { type: "element", value: "q8" },
          },
        ],
      };
      expect(
        evaluateLogic(
          mockSurvey,
          completeMatrixData,
          mockVariablesData,
          completelySubmittedCondition,
          "default"
        )
      ).toBe(true);
    });

    test("handles invalid or error conditions gracefully", () => {
      // Test with an invalid operator that would cause an error
      const invalidCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            // @ts-ignore - intentionally using invalid operator for test
            operator: "invalidOperator",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "static", value: "test" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, invalidCondition, "default")).toBe(false);

      // Test with a non-existent question
      const nonExistentCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "equals",
            leftOperand: { type: "element", value: "nonExistentId" },
            rightOperand: { type: "static", value: "test" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, nonExistentCondition, "default")).toBe(
        false
      );
    });

    test("evaluates OpinionScale numeric comparison operators", () => {
      // OpinionScale element is included in mockSurvey block1 with id "qOpinionScale"
      const opinionScaleData: TResponseData = {
        qOpinionScale: 4,
      };

      // Test equals: value 4 equals 4 → true
      const equalsCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "equals",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 4 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, opinionScaleData, mockVariablesData, equalsCondition, "default")).toBe(
        true
      );

      // Test doesNotEqual: value 4 doesNotEqual 5 → true
      const doesNotEqualCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "doesNotEqual",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 5 },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, opinionScaleData, mockVariablesData, doesNotEqualCondition, "default")
      ).toBe(true);

      // Test isGreaterThan: value 4 isGreaterThan 3 → true
      const greaterThanCondition: TConditionGroup = {
        id: "group3",
        connector: "and",
        conditions: [
          {
            id: "condition3",
            operator: "isGreaterThan",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 3 },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, opinionScaleData, mockVariablesData, greaterThanCondition, "default")
      ).toBe(true);

      // Test isLessThan: value 4 isLessThan 5 → true
      const lessThanCondition: TConditionGroup = {
        id: "group4",
        connector: "and",
        conditions: [
          {
            id: "condition4",
            operator: "isLessThan",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 5 },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, opinionScaleData, mockVariablesData, lessThanCondition, "default")
      ).toBe(true);

      // Test isGreaterThanOrEqual: value 4 isGreaterThanOrEqual 4 → true
      const greaterThanOrEqualCondition: TConditionGroup = {
        id: "group5",
        connector: "and",
        conditions: [
          {
            id: "condition5",
            operator: "isGreaterThanOrEqual",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 4 },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, opinionScaleData, mockVariablesData, greaterThanOrEqualCondition, "default")
      ).toBe(true);

      // Test isLessThanOrEqual: value 4 isLessThanOrEqual 4 → true
      const lessThanOrEqualCondition: TConditionGroup = {
        id: "group6",
        connector: "and",
        conditions: [
          {
            id: "condition6",
            operator: "isLessThanOrEqual",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 4 },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, opinionScaleData, mockVariablesData, lessThanOrEqualCondition, "default")
      ).toBe(true);
    });

    test("evaluates OpinionScale isSubmitted and isSkipped operators", () => {
      // Test isSubmitted with value 4 → true
      const submittedData: TResponseData = {
        qOpinionScale: 4,
      };
      const isSubmittedCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "isSubmitted",
            leftOperand: { type: "element", value: "qOpinionScale" },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, submittedData, mockVariablesData, isSubmittedCondition, "default")
      ).toBe(true);

      // Test isSkipped with undefined value → true
      const skippedData: TResponseData = {};
      const isSkippedCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "isSkipped",
            leftOperand: { type: "element", value: "qOpinionScale" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, skippedData, mockVariablesData, isSkippedCondition, "default")).toBe(
        true
      );
    });

    test("evaluates Payment isSubmitted and isSkipped operators", () => {
      // Test isSubmitted with value "paid" → true
      const paidData: TResponseData = {
        qPayment: "paid",
      };
      const isSubmittedCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "isSubmitted",
            leftOperand: { type: "element", value: "qPayment" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, paidData, mockVariablesData, isSubmittedCondition, "default")).toBe(
        true
      );

      // Test isSkipped with empty string → true
      const skippedData: TResponseData = {
        qPayment: "",
      };
      const isSkippedCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "isSkipped",
            leftOperand: { type: "element", value: "qPayment" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, skippedData, mockVariablesData, isSkippedCondition, "default")).toBe(
        true
      );

      // Test isSubmitted with empty string → false
      expect(evaluateLogic(mockSurvey, skippedData, mockVariablesData, isSubmittedCondition, "default")).toBe(
        false
      );
    });
  });

  describe("Edge Cases", () => {
    const mockData: TResponseData = {
      q1: "test answer",
      q2: "42",
      q3: "opt1",
      q4: ["Option 1", "Option 2"],
      q5: "2023-01-01",
      q6: "file-url.pdf",
      q7: ["pic1", "pic2"],
      q8: { "Row 1": "Column 1", "Row 2": "Column 2" },
      fieldId1: "hidden value",
      emptyField: "",
      dateField: "2023-05-01",
    };

    const mockVariablesData: TResponseVariables = {
      var1: "string value",
      var2: 50,
      var3: "",
      numVar: 123,
      dateVar: "2023-06-01",
    };

    test("evaluates matrix question with invalid row id", () => {
      const matrixCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "equals",
            leftOperand: {
              type: "element",
              value: "q8",
              meta: { row: "invalid-row" },
            },
            rightOperand: { type: "static", value: "0" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, matrixCondition, "default")).toBe(false);
    });

    test("evaluates invalid row index for matrix question", () => {
      const matrixCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "equals",
            leftOperand: {
              type: "element",
              value: "q8",
              meta: { row: "99" }, // Invalid row index
            },
            rightOperand: { type: "static", value: "1" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, matrixCondition, "default")).toBe(false);
    });

    test("evaluates matrix question with empty row value", () => {
      const emptyMatrixData: TResponseData = {
        q8: { "Row 1": "" },
      };

      const matrixCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "isEmpty",
            leftOperand: {
              type: "element",
              value: "q8",
              meta: { row: "0" },
            },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, emptyMatrixData, mockVariablesData, matrixCondition, "default")).toBe(
        true
      );
    });

    test("evaluates doesNotEqual with picture selection", () => {
      const condition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "doesNotEqual",
            leftOperand: { type: "element", value: "q7" },
            rightOperand: { type: "static", value: "option2" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, condition, "default")).toBe(true);
    });

    test("evaluates date conditions between questions", () => {
      // Tests date comparisons between two questions
      const dateData: TResponseData = {
        dateQ1: "2023-01-01",
        dateQ2: "2023-02-01",
      };

      // Test for equals operator
      const equalsDateCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "equals",
            leftOperand: { type: "element", value: "dateQ1" },
            rightOperand: { type: "element", value: "dateQ2" },
          },
        ],
      };

      // Mock survey with date questions
      const dateSurvey: TJsEnvironmentStateSurvey = {
        ...mockSurvey,
        blocks: [
          ...mockSurvey.blocks,
          {
            id: "dateBlock",
            name: "Date Block",
            elements: [
              {
                id: "dateQ1",
                type: TSurveyElementTypeEnum.Date,
                headline: { default: "Date Question 1" },
                required: true,
                format: "d-M-y",
              },
              {
                id: "dateQ2",
                type: TSurveyElementTypeEnum.Date,
                headline: { default: "Date Question 2" },
                required: true,
                format: "d-M-y",
              },
            ],
          },
        ],
      };

      expect(evaluateLogic(dateSurvey, dateData, mockVariablesData, equalsDateCondition, "default")).toBe(
        false
      );

      // Test for doesNotEqual operator
      const doesNotEqualDateCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "doesNotEqual",
            leftOperand: { type: "element", value: "dateQ1" },
            rightOperand: { type: "element", value: "dateQ2" },
          },
        ],
      };
      expect(
        evaluateLogic(dateSurvey, dateData, mockVariablesData, doesNotEqualDateCondition, "default")
      ).toBe(true);
    });

    test("evaluates multiple choice conditions for equals/doesNotEqual", () => {
      // Tests for array equals/doesNotEqual operations
      const multiChoiceData: TResponseData = {
        singleValue: "option1",
        multiValue: ["option1", "option2"],
      };

      const multiSurvey: TJsEnvironmentStateSurvey = {
        ...mockSurvey,
        blocks: [
          ...mockSurvey.blocks,
          {
            id: "multiBlock",
            name: "Multi Choice Block",
            elements: [
              {
                id: "multiQ",
                type: TSurveyElementTypeEnum.MultipleChoiceMulti,
                headline: { default: "Multiple Choice" },
                required: true,
                choices: [
                  { id: "opt1", label: { default: "Option 1" } },
                  { id: "opt2", label: { default: "Option 2" } },
                ],
              },
            ],
          },
        ],
      };

      // Test equals with array length 1 and string
      const equalsArrayCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "equals",
            leftOperand: { type: "element", value: "multiValue" },
            rightOperand: { type: "static", value: "option1" },
          },
        ],
      };
      expect(
        evaluateLogic(multiSurvey, multiChoiceData, mockVariablesData, equalsArrayCondition, "default")
      ).toBe(false);

      // Test with right operand as multiple choice
      const equalsMultiCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "equals",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "element", value: "multiQ" },
          },
        ],
      };
      const multiChoiceTestData = {
        multiQ: ["option1"],
      };
      expect(
        evaluateLogic(multiSurvey, multiChoiceTestData, mockVariablesData, equalsMultiCondition, "default")
      ).toBe(false);
    });

    test("evaluates isEmpty and isNotEmpty operators", () => {
      // Test isEmpty
      const isEmptyCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "isEmpty",
            leftOperand: { type: "element", value: "q1" },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, { ...mockData, q1: "" }, mockVariablesData, isEmptyCondition, "default")
      ).toBe(true);

      // Test isNotEmpty
      const isNotEmptyCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "isNotEmpty",
            leftOperand: { type: "element", value: "q1" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, isNotEmptyCondition, "default")).toBe(
        true
      );
    });

    test("evaluates isAnyOf operator", () => {
      const isAnyOfCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "isAnyOf",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "static", value: ["wrong answer", "test answer", "another answer"] },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, isAnyOfCondition, "default")).toBe(true);

      // Test isAnyOf with non-array right value
      const invalidIsAnyOfCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "isAnyOf",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "static", value: "test answer" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, mockData, mockVariablesData, invalidIsAnyOfCondition, "default")).toBe(
        false
      );
    });

    test("getLeftOperandValue with edge cases", () => {
      const specialSurvey: TJsEnvironmentStateSurvey = {
        ...mockSurvey,
        blocks: [
          ...mockSurvey.blocks,
          {
            id: "specialBlock",
            name: "Special Block",
            elements: [
              {
                id: "multiChoiceWithOther",
                type: TSurveyElementTypeEnum.MultipleChoiceSingle,
                headline: { default: "Multiple Choice With Other" },
                required: true,
                choices: [
                  { id: "opt1", label: { default: "Option 1" } },
                  { id: "opt2", label: { default: "Option 2" } },
                  { id: "other", label: { default: "Other" } },
                ],
              },
            ],
          },
        ],
      };

      const otherOptionCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "equals",
            leftOperand: { type: "element", value: "multiChoiceWithOther" },
            rightOperand: { type: "static", value: "Custom Option" },
          },
        ],
      };

      const otherOptionData = {
        multiChoiceWithOther: "Custom Option",
      };

      expect(
        evaluateLogic(specialSurvey, otherOptionData, mockVariablesData, otherOptionCondition, "default")
      ).toBe(false);

      const multiChoiceArrayCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "equals",
            leftOperand: { type: "element", value: "multiChoiceWithOther" },
            rightOperand: { type: "static", value: "opt1" },
          },
        ],
      };

      const multiChoiceArrayData = {
        multiChoiceWithOther: ["Option 1"],
      };

      expect(
        evaluateLogic(
          specialSurvey,
          multiChoiceArrayData,
          mockVariablesData,
          multiChoiceArrayCondition,
          "default"
        )
      ).toBe(true);
    });

    test("evaluates OpinionScale with string-coerced numeric values", () => {
      // OpinionScale values stored as strings should be coerced to numbers for comparison
      const stringCoercedData: TResponseData = {
        qOpinionScale: "4",
      };

      // Test equals: string "4" coerced to number 4, compared to 4 → true
      const equalsCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "equals",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 4 },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, stringCoercedData, mockVariablesData, equalsCondition, "default")
      ).toBe(true);

      // Test isGreaterThan: string "4" coerced to number 4, compared to 3 → true
      const greaterThanCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "isGreaterThan",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 3 },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, stringCoercedData, mockVariablesData, greaterThanCondition, "default")
      ).toBe(true);
    });

    test("evaluates OpinionScale with undefined response", () => {
      // When no response is provided for an OpinionScale, the value should be undefined
      const undefinedData: TResponseData = {};

      // Test isSkipped with undefined → true
      const isSkippedCondition: TConditionGroup = {
        id: "group1",
        connector: "and",
        conditions: [
          {
            id: "condition1",
            operator: "isSkipped",
            leftOperand: { type: "element", value: "qOpinionScale" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, undefinedData, mockVariablesData, isSkippedCondition, "default")).toBe(
        true
      );

      // Test isSubmitted with undefined → false (numeric leftValue is undefined, not a number)
      const isSubmittedCondition: TConditionGroup = {
        id: "group2",
        connector: "and",
        conditions: [
          {
            id: "condition2",
            operator: "isSubmitted",
            leftOperand: { type: "element", value: "qOpinionScale" },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, undefinedData, mockVariablesData, isSubmittedCondition, "default")
      ).toBe(false);
    });
  });

  describe("OpinionScale and Payment - Sprint 2 Comprehensive Coverage", () => {
    const mockVariablesData: TResponseVariables = {
      var1: "string value",
      var2: 123,
      var3: "another string",
    };

    test("evaluates OpinionScale with boundary values for all numeric operators", () => {
      // value=1: boundary minimum
      const data1: TResponseData = { qOpinionScale: 1 };

      // equals 1 → true
      const equals1: TConditionGroup = {
        id: "g1",
        connector: "and",
        conditions: [
          {
            id: "c1",
            operator: "equals",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 1 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, data1, mockVariablesData, equals1, "default")).toBe(true);

      // isLessThan 2 → true
      const lessThan2: TConditionGroup = {
        id: "g2",
        connector: "and",
        conditions: [
          {
            id: "c2",
            operator: "isLessThan",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 2 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, data1, mockVariablesData, lessThan2, "default")).toBe(true);

      // isGreaterThan 0 → true
      const greaterThan0: TConditionGroup = {
        id: "g3",
        connector: "and",
        conditions: [
          {
            id: "c3",
            operator: "isGreaterThan",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 0 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, data1, mockVariablesData, greaterThan0, "default")).toBe(true);

      // value=5: mid-range
      const data5: TResponseData = { qOpinionScale: 5 };

      // equals 5 → true
      const equals5: TConditionGroup = {
        id: "g4",
        connector: "and",
        conditions: [
          {
            id: "c4",
            operator: "equals",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 5 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, data5, mockVariablesData, equals5, "default")).toBe(true);

      // isGreaterThanOrEqual 5 → true
      const gte5: TConditionGroup = {
        id: "g5",
        connector: "and",
        conditions: [
          {
            id: "c5",
            operator: "isGreaterThanOrEqual",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 5 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, data5, mockVariablesData, gte5, "default")).toBe(true);

      // isLessThanOrEqual 5 → true
      const lte5: TConditionGroup = {
        id: "g6",
        connector: "and",
        conditions: [
          {
            id: "c6",
            operator: "isLessThanOrEqual",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 5 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, data5, mockVariablesData, lte5, "default")).toBe(true);

      // value=7: above mid-range
      const data7: TResponseData = { qOpinionScale: 7 };

      // isGreaterThan 5 → true
      const gt5: TConditionGroup = {
        id: "g7",
        connector: "and",
        conditions: [
          {
            id: "c7",
            operator: "isGreaterThan",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 5 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, data7, mockVariablesData, gt5, "default")).toBe(true);

      // isLessThan 10 → true
      const lt10: TConditionGroup = {
        id: "g8",
        connector: "and",
        conditions: [
          {
            id: "c8",
            operator: "isLessThan",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 10 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, data7, mockVariablesData, lt10, "default")).toBe(true);

      // doesNotEqual 3 → true
      const dne3: TConditionGroup = {
        id: "g9",
        connector: "and",
        conditions: [
          {
            id: "c9",
            operator: "doesNotEqual",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 3 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, data7, mockVariablesData, dne3, "default")).toBe(true);

      // value=10: boundary maximum
      const data10: TResponseData = { qOpinionScale: 10 };

      // isGreaterThanOrEqual 10 → true
      const gte10: TConditionGroup = {
        id: "g10",
        connector: "and",
        conditions: [
          {
            id: "c10",
            operator: "isGreaterThanOrEqual",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 10 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, data10, mockVariablesData, gte10, "default")).toBe(true);

      // isLessThanOrEqual 10 → true
      const lte10: TConditionGroup = {
        id: "g11",
        connector: "and",
        conditions: [
          {
            id: "c11",
            operator: "isLessThanOrEqual",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 10 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, data10, mockVariablesData, lte10, "default")).toBe(true);

      // isGreaterThan 10 → false (boundary: not strictly greater)
      const gt10: TConditionGroup = {
        id: "g12",
        connector: "and",
        conditions: [
          {
            id: "c12",
            operator: "isGreaterThan",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 10 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, data10, mockVariablesData, gt10, "default")).toBe(false);
    });

    test("evaluates OpinionScale numeric edge cases", () => {
      // Exact boundary: isGreaterThanOrEqual at boundary → true
      const boundaryData: TResponseData = { qOpinionScale: 5 };
      const gteAtBoundary: TConditionGroup = {
        id: "g1",
        connector: "and",
        conditions: [
          {
            id: "c1",
            operator: "isGreaterThanOrEqual",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 5 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, boundaryData, mockVariablesData, gteAtBoundary, "default")).toBe(true);

      // isLessThanOrEqual at boundary → true
      const lteAtBoundary: TConditionGroup = {
        id: "g2",
        connector: "and",
        conditions: [
          {
            id: "c2",
            operator: "isLessThanOrEqual",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 5 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, boundaryData, mockVariablesData, lteAtBoundary, "default")).toBe(true);

      // isGreaterThan at boundary → false (strict inequality fails at boundary)
      const gtAtBoundary: TConditionGroup = {
        id: "g3",
        connector: "and",
        conditions: [
          {
            id: "c3",
            operator: "isGreaterThan",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 5 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, boundaryData, mockVariablesData, gtAtBoundary, "default")).toBe(false);

      // Value as 0: getLeftOperandValue returns 0 (valid number, not NaN)
      const zeroData: TResponseData = { qOpinionScale: 0 };

      // equals 0 → true
      const equalsZero: TConditionGroup = {
        id: "g4",
        connector: "and",
        conditions: [
          {
            id: "c4",
            operator: "equals",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 0 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, zeroData, mockVariablesData, equalsZero, "default")).toBe(true);

      // isGreaterThan 0 → false (0 is not greater than 0)
      const gtZero: TConditionGroup = {
        id: "g5",
        connector: "and",
        conditions: [
          {
            id: "c5",
            operator: "isGreaterThan",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 0 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, zeroData, mockVariablesData, gtZero, "default")).toBe(false);

      // isLessThan 1 → true
      const ltOne: TConditionGroup = {
        id: "g6",
        connector: "and",
        conditions: [
          {
            id: "c6",
            operator: "isLessThan",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 1 },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, zeroData, mockVariablesData, ltOne, "default")).toBe(true);

      // isSubmitted with value 0 → true (typeof 0 === "number" → leftValue !== null → true)
      const isSubmittedZero: TConditionGroup = {
        id: "g7",
        connector: "and",
        conditions: [
          {
            id: "c7",
            operator: "isSubmitted",
            leftOperand: { type: "element", value: "qOpinionScale" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, zeroData, mockVariablesData, isSubmittedZero, "default")).toBe(true);

      // NaN handling: "not-a-number" string coerces to NaN, getLeftOperandValue returns undefined
      const nanData: TResponseData = { qOpinionScale: "not-a-number" };

      // isSkipped with NaN string → true (NaN coerced to undefined by getLeftOperandValue)
      const isSkippedNaN: TConditionGroup = {
        id: "g8",
        connector: "and",
        conditions: [
          {
            id: "c8",
            operator: "isSkipped",
            leftOperand: { type: "element", value: "qOpinionScale" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, nanData, mockVariablesData, isSkippedNaN, "default")).toBe(true);

      // isSubmitted with NaN string → false (undefined → not string/array/number → returns false)
      const isSubmittedNaN: TConditionGroup = {
        id: "g9",
        connector: "and",
        conditions: [
          {
            id: "c9",
            operator: "isSubmitted",
            leftOperand: { type: "element", value: "qOpinionScale" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, nanData, mockVariablesData, isSubmittedNaN, "default")).toBe(false);
    });

    test("evaluates Payment element edge cases", () => {
      // isSubmitted with "pending" → true (non-empty string !== "" && !== null)
      const isSubmittedCond: TConditionGroup = {
        id: "g1",
        connector: "and",
        conditions: [
          {
            id: "c1",
            operator: "isSubmitted",
            leftOperand: { type: "element", value: "qPayment" },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, { qPayment: "pending" }, mockVariablesData, isSubmittedCond, "default")
      ).toBe(true);

      // isSubmitted with "failed" → true (non-empty string)
      expect(
        evaluateLogic(mockSurvey, { qPayment: "failed" }, mockVariablesData, isSubmittedCond, "default")
      ).toBe(true);

      // isSkipped condition for reuse
      const isSkippedCond: TConditionGroup = {
        id: "g2",
        connector: "and",
        conditions: [
          {
            id: "c2",
            operator: "isSkipped",
            leftOperand: { type: "element", value: "qPayment" },
          },
        ],
      };

      // isSkipped with null → true (runtime edge case: null values from database queries)
      expect(
        evaluateLogic(
          mockSurvey,
          { qPayment: null } as unknown as TResponseData,
          mockVariablesData,
          isSkippedCond,
          "default"
        )
      ).toBe(true);

      // isSkipped with undefined → true (key present but value is undefined)
      expect(
        evaluateLogic(mockSurvey, { qPayment: undefined }, mockVariablesData, isSkippedCond, "default")
      ).toBe(true);

      // isSkipped with empty response data → true (key not present → undefined)
      expect(evaluateLogic(mockSurvey, {}, mockVariablesData, isSkippedCond, "default")).toBe(true);

      // isSubmitted with empty response data → false (undefined → not string/array/number → false)
      expect(evaluateLogic(mockSurvey, {}, mockVariablesData, isSubmittedCond, "default")).toBe(false);
    });

    test("evaluates nested condition groups combining new element types with existing types", () => {
      // Test 1: OpinionScale > 3 AND q1 equals "test"
      const andCondition: TConditionGroup = {
        id: "andGroup",
        connector: "and",
        conditions: [
          {
            id: "c1",
            operator: "isGreaterThan",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 3 },
          },
          {
            id: "c2",
            operator: "equals",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "static", value: "test" },
          },
        ],
      };
      // Both conditions met → true
      expect(
        evaluateLogic(
          mockSurvey,
          { qOpinionScale: 4, q1: "test" },
          mockVariablesData,
          andCondition,
          "default"
        )
      ).toBe(true);
      // OpinionScale fails → false
      expect(
        evaluateLogic(
          mockSurvey,
          { qOpinionScale: 2, q1: "test" },
          mockVariablesData,
          andCondition,
          "default"
        )
      ).toBe(false);

      // Test 2: Payment isSubmitted OR q2 isGreaterThan 10
      const orCondition: TConditionGroup = {
        id: "orGroup",
        connector: "or",
        conditions: [
          {
            id: "c3",
            operator: "isSubmitted",
            leftOperand: { type: "element", value: "qPayment" },
          },
          {
            id: "c4",
            operator: "isGreaterThan",
            leftOperand: { type: "element", value: "q2" },
            rightOperand: { type: "static", value: 10 },
          },
        ],
      };
      // Payment submitted → true (first condition met)
      expect(
        evaluateLogic(mockSurvey, { qPayment: "paid", q2: "5" }, mockVariablesData, orCondition, "default")
      ).toBe(true);
      // q2 > 10 → true (second condition met)
      expect(
        evaluateLogic(mockSurvey, { qPayment: "", q2: "15" }, mockVariablesData, orCondition, "default")
      ).toBe(true);
      // Both conditions fail → false
      expect(
        evaluateLogic(mockSurvey, { qPayment: "", q2: "5" }, mockVariablesData, orCondition, "default")
      ).toBe(false);

      // Test 3: Complex nested groups: (OpinionScale >= 4 AND Payment isSubmitted) OR q1 equals "test"
      const innerAndGroup: TConditionGroup = {
        id: "innerAnd",
        connector: "and",
        conditions: [
          {
            id: "c5",
            operator: "isGreaterThanOrEqual",
            leftOperand: { type: "element", value: "qOpinionScale" },
            rightOperand: { type: "static", value: 4 },
          },
          {
            id: "c6",
            operator: "isSubmitted",
            leftOperand: { type: "element", value: "qPayment" },
          },
        ],
      };
      const nestedCondition: TConditionGroup = {
        id: "outerOr",
        connector: "or",
        conditions: [
          innerAndGroup,
          {
            id: "c7",
            operator: "equals",
            leftOperand: { type: "element", value: "q1" },
            rightOperand: { type: "static", value: "test" },
          },
        ],
      };
      // Inner AND group true → overall true
      expect(
        evaluateLogic(
          mockSurvey,
          { qOpinionScale: 5, qPayment: "paid", q1: "other" },
          mockVariablesData,
          nestedCondition,
          "default"
        )
      ).toBe(true);
      // q1 equals "test" → overall true
      expect(
        evaluateLogic(
          mockSurvey,
          { qOpinionScale: 2, qPayment: "", q1: "test" },
          mockVariablesData,
          nestedCondition,
          "default"
        )
      ).toBe(true);
      // All conditions fail → false
      expect(
        evaluateLogic(
          mockSurvey,
          { qOpinionScale: 2, qPayment: "", q1: "other" },
          mockVariablesData,
          nestedCondition,
          "default"
        )
      ).toBe(false);
    });

    test("evaluates empty and skipped responses across OpinionScale and Payment element types", () => {
      // OpinionScale with empty object response → isSkipped true
      const isSkippedOpinionScale: TConditionGroup = {
        id: "g1",
        connector: "and",
        conditions: [
          {
            id: "c1",
            operator: "isSkipped",
            leftOperand: { type: "element", value: "qOpinionScale" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, {}, mockVariablesData, isSkippedOpinionScale, "default")).toBe(true);

      // OpinionScale with empty object response → isSubmitted false
      const isSubmittedOpinionScale: TConditionGroup = {
        id: "g2",
        connector: "and",
        conditions: [
          {
            id: "c2",
            operator: "isSubmitted",
            leftOperand: { type: "element", value: "qOpinionScale" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, {}, mockVariablesData, isSubmittedOpinionScale, "default")).toBe(
        false
      );

      // Payment with empty string → isSkipped true
      const isSkippedPayment: TConditionGroup = {
        id: "g3",
        connector: "and",
        conditions: [
          {
            id: "c3",
            operator: "isSkipped",
            leftOperand: { type: "element", value: "qPayment" },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, { qPayment: "" }, mockVariablesData, isSkippedPayment, "default")
      ).toBe(true);

      // Payment with empty string → isSubmitted false
      const isSubmittedPayment: TConditionGroup = {
        id: "g4",
        connector: "and",
        conditions: [
          {
            id: "c4",
            operator: "isSubmitted",
            leftOperand: { type: "element", value: "qPayment" },
          },
        ],
      };
      expect(
        evaluateLogic(mockSurvey, { qPayment: "" }, mockVariablesData, isSubmittedPayment, "default")
      ).toBe(false);

      // Both missing from response → both isSkipped true (combined AND condition)
      const emptyResponse: TResponseData = {};
      const bothSkipped: TConditionGroup = {
        id: "g5",
        connector: "and",
        conditions: [
          {
            id: "c5",
            operator: "isSkipped",
            leftOperand: { type: "element", value: "qOpinionScale" },
          },
          {
            id: "c6",
            operator: "isSkipped",
            leftOperand: { type: "element", value: "qPayment" },
          },
        ],
      };
      expect(evaluateLogic(mockSurvey, emptyResponse, mockVariablesData, bothSkipped, "default")).toBe(true);
    });
  });
});
