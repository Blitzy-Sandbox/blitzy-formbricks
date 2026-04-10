import { z } from "zod";
import { extendZodWithOpenApi } from "zod-openapi";

extendZodWithOpenApi(z);

// ---------------------------------------------------------------------------
// 1. ZTypeformFieldDefinition — Field metadata in form definition
// ---------------------------------------------------------------------------
export const ZTypeformFieldDefinition = z
  .object({
    id: z.string().openapi({
      description: "Unique identifier for the field, maps to Formbricks question ID",
    }),
    title: z.string().openapi({
      description: "The display title of the field/question",
    }),
    type: z.string().openapi({
      description:
        "The field type (e.g., 'short_text', 'long_text', 'multiple_choice', 'number', 'rating', 'opinion_scale', 'date', 'email', 'file_upload', 'payment', 'yes_no', 'picture_choice', 'dropdown', 'ranking', 'matrix', 'cal', 'address', 'contact_info')",
    }),
    ref: z.string().openapi({
      description: "Reference identifier for the field, typically matches the field ID",
    }),
    properties: z.record(z.unknown()).optional().openapi({
      description: "Optional additional properties specific to the field type",
    }),
  })
  .openapi({
    ref: "typeformFieldDefinition",
    description: "A field definition within the form definition section of a Typeform-compatible payload",
  });

// ---------------------------------------------------------------------------
// 2. ZTypeformAnswer — Typed answer object
//    Supports all Formbricks element types mapped to Typeform answer types.
//    Exactly one type-specific value field will be present per answer.
// ---------------------------------------------------------------------------
export const ZTypeformAnswer = z
  .object({
    field: z
      .object({
        id: z.string().openapi({
          description: "The ID of the field this answer belongs to",
        }),
        type: z.string().openapi({
          description: "The type of the field this answer belongs to",
        }),
        ref: z.string().openapi({
          description: "The reference identifier of the field",
        }),
      })
      .openapi({
        description: "Reference to the field definition this answer corresponds to",
      }),
    type: z
      .enum(["text", "number", "boolean", "choice", "choices", "date", "email", "url", "file_url", "payment"])
      .openapi({
        description: "The answer value type",
      }),
    // Type-specific value fields — exactly one will be present per answer
    text: z.string().optional().openapi({
      description: "Text value for text-type answers",
    }),
    number: z.number().optional().openapi({
      description: "Numeric value for number-type answers",
    }),
    boolean: z.boolean().optional().openapi({
      description: "Boolean value for yes/no answers",
    }),
    choice: z
      .object({
        label: z.string(),
        other: z.string().optional(),
      })
      .optional()
      .openapi({
        description: "Single choice value with label",
      }),
    choices: z
      .object({
        labels: z.array(z.string()),
        other: z.string().optional(),
      })
      .optional()
      .openapi({
        description: "Multiple choice values with labels array",
      }),
    date: z.string().optional().openapi({
      description: "ISO 8601 date string for date-type answers",
    }),
    email: z.string().optional().openapi({
      description: "Email address for email-type answers",
    }),
    url: z.string().optional().openapi({
      description: "URL value for URL-type answers",
    }),
    file_url: z.string().optional().openapi({
      description: "File URL for file upload answers",
    }),
    payment: z
      .object({
        amount: z.string(),
        currency: z.string(),
        status: z.string(),
      })
      .optional()
      .openapi({
        description: "Payment details for payment-type answers",
      }),
  })
  .openapi({
    ref: "typeformAnswer",
    description: "A typed answer object in a Typeform-compatible webhook payload",
  });

// ---------------------------------------------------------------------------
// 3. ZTypeformVariable — Typed variable
// ---------------------------------------------------------------------------
export const ZTypeformVariable = z
  .object({
    key: z.string().openapi({
      description: "The variable key/name",
    }),
    type: z.enum(["number", "text"]).openapi({
      description: "The variable value type",
    }),
    number: z.number().optional().openapi({
      description: "Numeric value when type is 'number'",
    }),
    text: z.string().optional().openapi({
      description: "Text value when type is 'text'",
    }),
  })
  .openapi({
    ref: "typeformVariable",
    description: "A typed variable in a Typeform-compatible webhook payload",
  });

// ---------------------------------------------------------------------------
// 4. ZTypeformHiddenFields — Hidden fields key-value map
// ---------------------------------------------------------------------------
export const ZTypeformHiddenFields = z.record(z.string()).openapi({
  ref: "typeformHiddenFields",
  description: "Hidden field key-value pairs passed via URL parameters",
});

// ---------------------------------------------------------------------------
// 5. ZTypeformCalculated — Calculated fields
// ---------------------------------------------------------------------------
export const ZTypeformCalculated = z
  .object({
    score: z.number().openapi({
      description: "The calculated score for the response",
    }),
  })
  .openapi({
    ref: "typeformCalculated",
    description: "Calculated fields in a Typeform-compatible webhook payload",
  });

// ---------------------------------------------------------------------------
// 6. ZTypeformDefinition — Form definition (composes ZTypeformFieldDefinition)
// ---------------------------------------------------------------------------
export const ZTypeformDefinition = z
  .object({
    id: z.string().openapi({
      description: "The form/survey ID",
    }),
    title: z.string().openapi({
      description: "The form/survey title",
    }),
    fields: z.array(ZTypeformFieldDefinition).openapi({
      description: "Array of field definitions in the form",
    }),
  })
  .openapi({
    ref: "typeformDefinition",
    description: "Form definition section of a Typeform-compatible webhook payload",
  });

// ---------------------------------------------------------------------------
// 7. ZTypeformCompatiblePayload — Complete payload
//    Composes all sub-schemas into the top-level Typeform-compatible structure.
// ---------------------------------------------------------------------------
export const ZTypeformCompatiblePayload = z
  .object({
    event_id: z.string().openapi({
      description: "Unique event identifier (UUID v7)",
    }),
    event_type: z.string().openapi({
      description: "The type of event (e.g., 'form_response')",
    }),
    form_id: z.string().openapi({
      description: "The survey/form ID",
    }),
    landed_at: z.string().openapi({
      description: "ISO 8601 timestamp when the respondent first opened the survey",
    }),
    submitted_at: z.string().openapi({
      description: "ISO 8601 timestamp when the response was submitted",
    }),
    definition: ZTypeformDefinition.openapi({
      description: "The form definition including field metadata",
    }),
    answers: z.array(ZTypeformAnswer).openapi({
      description: "Array of typed answer objects",
    }),
    hidden: ZTypeformHiddenFields.openapi({
      description: "Hidden field values",
    }),
    variables: z.array(ZTypeformVariable).openapi({
      description: "Array of typed variable values",
    }),
    calculated: ZTypeformCalculated.openapi({
      description: "Calculated fields including score",
    }),
  })
  .openapi({
    ref: "typeformCompatiblePayload",
    description: "Complete Typeform-compatible webhook payload structure",
  });

// ---------------------------------------------------------------------------
// TypeScript type inference — all types derived from Zod via z.infer<>
// ---------------------------------------------------------------------------
export type TTypeformFieldDefinition = z.infer<typeof ZTypeformFieldDefinition>;
export type TTypeformAnswer = z.infer<typeof ZTypeformAnswer>;
export type TTypeformVariable = z.infer<typeof ZTypeformVariable>;
export type TTypeformHiddenFields = z.infer<typeof ZTypeformHiddenFields>;
export type TTypeformCalculated = z.infer<typeof ZTypeformCalculated>;
export type TTypeformDefinition = z.infer<typeof ZTypeformDefinition>;
export type TTypeformCompatiblePayload = z.infer<typeof ZTypeformCompatiblePayload>;
