# Understanding OpenAPI YAML Structure

This guide explains the structure of `openapi.yaml` using examples from this codebase.

## 📋 Table of Contents
1. [Overall Structure](#overall-structure)
2. [Top-Level Sections](#top-level-sections)
3. [Paths Section](#paths-section)
4. [Components & Schemas](#components--schemas)
5. [Key Concepts](#key-concepts)

---

## 🏗️ Overall Structure

An OpenAPI file has 4 main sections:

```yaml
openapi: 3.0.3          # Version declaration
info: {...}             # API metadata
tags: [...]             # Endpoint groupings
paths: {...}            # API endpoints
components: {...}       # Reusable definitions
```

---

## 📝 Top-Level Sections

### 1. `openapi` - Version Declaration
```yaml
openapi: 3.0.3
```
- Specifies the OpenAPI specification version
- Must be the first line

### 2. `info` - API Metadata
```yaml
info:
  title: TinBoker API
  description: |
    API for TinBoker - Stock relationship visualization platform.
  version: 1.0.0
  contact:
    name: TinBoker Team
```
- **title**: Name of your API
- **description**: What your API does (supports multi-line with `|`)
- **version**: API version (not OpenAPI version)
- **contact**: Who to contact about the API

### 3. `tags` - Endpoint Groupings
```yaml
tags:
  - name: Concepts
    description: Industry concept endpoints
  - name: Companies
    description: Company data endpoints
```
- Groups related endpoints together in documentation
- Used in the `paths` section to tag endpoints

---

## 🛣️ Paths Section

The `paths` section defines all your API endpoints. Each path can have multiple HTTP methods.

### Basic Path Structure
```yaml
paths:
  /endpoint-name:
    get:          # HTTP method (get, post, put, delete, etc.)
      summary: "Short description"
      description: "Longer description"
      operationId: "uniqueOperationName"
      tags: ["TagName"]
      parameters: [...]
      responses: {...}
```

### Example: Simple GET Endpoint
```yaml
/concepts:
  get:
    tags:
      - Concepts
    summary: Get available concepts
    description: Retrieve the list of industry concepts/graphs
    operationId: getConcepts
    responses:
      '200':
        description: List of available concepts
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ConceptsResponse'
```

**Breaking it down:**
- `/concepts` - The URL path
- `get:` - HTTP method
- `tags:` - Groups this endpoint in docs
- `summary:` - Short description (appears in docs)
- `description:` - Detailed explanation
- `operationId:` - Unique identifier (used in code generation)
- `responses:` - What the API returns

### Example: Path with Parameters
```yaml
/company/{ticker}:
  get:
    parameters:
      - name: ticker
        in: path              # Parameter location
        required: true
        description: Stock ticker symbol (e.g., TSLA, NVDA)
        schema:
          type: string
          pattern: '^[A-Z]+$'  # Validation pattern
          example: TSLA
    responses:
      '200':
        description: Company details
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CompanyResponse'
      '404':
        description: Company not found
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ErrorResponse'
```

**Parameter locations:**
- `in: path` - URL path parameter: `/company/TSLA`
- `in: query` - Query string: `/events?tickers=TSLA,NVDA`
- `in: header` - HTTP header
- `in: cookie` - Cookie value

### Example: Query Parameters
```yaml
/events:
  get:
    parameters:
      - name: tickers
        in: query
        required: false
        description: Comma-separated list of ticker symbols
        schema:
          type: string
          example: TSLA,NVDA
```

---

## 🧩 Components & Schemas

The `components` section contains reusable definitions. This prevents repetition and keeps your spec DRY.

### Schema Structure
```yaml
components:
  schemas:
    SchemaName:
      type: object          # object, array, string, number, boolean, integer
      description: "What this represents"
      required:             # Required fields
        - field1
        - field2
      properties:           # Field definitions
        field1:
          type: string
          description: "Field description"
          example: "example value"
        field2:
          type: number
          format: double
```

### Example: Simple Schema
```yaml
Position:
  type: object
  description: 2D position coordinates
  required:
    - x
    - y
  properties:
    x:
      type: number
      description: X coordinate
      example: 0
    y:
      type: number
      description: Y coordinate
      example: 0
```

### Example: Schema with Enum
```yaml
GraphNode:
  type: object
  required:
    - id
    - type
    - data
    - position
  properties:
    id:
      type: string
      example: TSLA
    type:
      type: string
      enum:                    # Allowed values
        - company
        - stock
        - cluster
      example: stock
    data:
      $ref: '#/components/schemas/GraphNodeData'  # Reference to another schema
    position:
      $ref: '#/components/schemas/Position'
```

### Example: Array Schema
```yaml
ConceptsResponse:
  type: object
  required:
    - data
    - timestamp
  properties:
    data:
      type: array
      items:                  # What each array item looks like
        $ref: '#/components/schemas/ConceptMetadata'
    timestamp:
      type: string
      format: date-time
```

### Example: Nested Objects
```yaml
ErrorResponse:
  type: object
  required:
    - error
  properties:
    error:
      type: object           # Nested object
      required:
        - code
        - message
      properties:
        code:
          type: string
        message:
          type: string
```

---

## 🔑 Key Concepts

### 1. **$ref - References**
Instead of repeating schemas, use `$ref` to reference them:

```yaml
# Define once
Position:
  type: object
  properties:
    x: { type: number }
    y: { type: number }

# Reference it
GraphNode:
  properties:
    position:
      $ref: '#/components/schemas/Position'  # Points to Position schema
```

**Reference syntax:**
- `#/components/schemas/SchemaName` - Reference within same file
- `./other-file.yaml#/components/schemas/SchemaName` - External file

### 2. **Data Types**
```yaml
type: string      # Text
type: number      # Decimal number
type: integer     # Whole number
type: boolean     # true/false
type: object      # JSON object
type: array       # List of items
```

### 3. **Formats**
```yaml
format: date-time    # ISO 8601 datetime
format: date         # YYYY-MM-DD
format: double       # Floating point
format: int64        # 64-bit integer
format: email        # Email address
format: uri          # URL
```

### 4. **Response Status Codes**
```yaml
responses:
  '200':           # Success
    description: OK
  '201':           # Created
    description: Created
  '400':           # Bad Request
    description: Invalid input
  '404':           # Not Found
    description: Resource not found
  '500':           # Server Error
    description: Internal error
```

### 5. **Required vs Optional Fields**
```yaml
MySchema:
  required:           # These fields MUST be present
    - id
    - name
  properties:
    id:
      type: string
    name:
      type: string
    description:      # Not in required = optional
      type: string
```

---

## 📊 Real Example from Your File

Let's trace a complete example:

### 1. The Endpoint Definition
```yaml
/company/{ticker}:
  get:
    parameters:
      - name: ticker
        in: path
        required: true
    responses:
      '200':
        schema:
          $ref: '#/components/schemas/CompanyResponse'
```

### 2. The Response Schema
```yaml
CompanyResponse:
  type: object
  required:
    - data
    - timestamp
  properties:
    data:
      $ref: '#/components/schemas/CompanyDetail'  # References another schema
    timestamp:
      type: string
      format: date-time
```

### 3. The Nested Schema
```yaml
CompanyDetail:
  type: object
  required:
    - ticker
    - name
    - price
  properties:
    ticker:
      type: string
      example: TSLA
    name:
      type: string
      example: Tesla Inc.
    price:
      type: number
      format: double
      example: 242.84
```

**Flow:**
1. Client calls: `GET /company/TSLA`
2. API returns: `CompanyResponse` format
3. Which contains: `CompanyDetail` in the `data` field
4. Plus: `timestamp` field

---

## 🎯 Common Patterns

### Pattern 1: Standard Response Wrapper
```yaml
StandardResponse:
  type: object
  required:
    - data
    - timestamp
  properties:
    data: { ... }           # Actual response data
    timestamp:              # When response was generated
      type: string
      format: date-time
```

### Pattern 2: Error Response
```yaml
ErrorResponse:
  type: object
  required:
    - error
  properties:
    error:
      type: object
      required:
        - code
        - message
      properties:
        code: { type: string }
        message: { type: string }
```

### Pattern 3: Paginated Response
```yaml
PaginatedResponse:
  type: object
  properties:
    data:
      type: array
      items: { ... }
    page:
      type: integer
    pageSize:
      type: integer
    total:
      type: integer
```

---

## 🔍 How to Read Your OpenAPI File

1. **Start with `paths`** - See what endpoints exist
2. **Check `operationId`** - Understand what each endpoint does
3. **Follow `$ref` links** - Trace schema references
4. **Check `required` fields** - Know what's mandatory
5. **Look at `examples`** - See expected data format

---

## 💡 Tips

1. **Use `$ref` liberally** - Don't repeat yourself
2. **Add descriptions** - Help developers understand
3. **Use enums** - Restrict values when possible
4. **Include examples** - Show real data formats
5. **Group with tags** - Organize related endpoints
6. **Validate with patterns** - Use regex for strings when needed

---

## 🛠️ Tools That Use OpenAPI

- **Swagger UI** - Interactive API documentation
- **Postman** - Import APIs for testing
- **Code Generators** - Generate client/server code
- **API Testing** - Validate implementations
- **FastAPI** - Can auto-generate OpenAPI from code

---

## 📚 Additional Resources

- [OpenAPI 3.0 Specification](https://swagger.io/specification/)
- [OpenAPI Guide](https://swagger.io/docs/specification/about/)
- [JSON Schema](https://json-schema.org/) - Schema validation standard

