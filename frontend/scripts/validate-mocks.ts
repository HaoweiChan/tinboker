import { ZodError } from 'zod';

import {
  ConceptMetadataSchema,
  CompanyDetailSchema,
  GraphDataSchema,
  StockEventSchema,
  TopMoverSchema,
  SectorBubbleDataSchema,
  SectorPerformanceStatsSchema,
  TreeMapItemSchema,
  VisualGraphDataSchema,
  InteractiveModelDataSchema,
} from '@/validation/schemas';
import {
  mockConcepts,
  mockCompanyDetails,
  mockGraphData,
  mockStockEvents,
  mockTopMovers,
  getSectorBubbleData,
  getSectorPerformanceStats,
  getTreeMapData,
  getSupplyChainData,
  getOwnershipData,
  getClusterData,
  INTERACTIVE_MODEL_LIST,
} from '@/services/mocks';

type Validation = {
  name: string;
  run: () => void;
};

const validations: Validation[] = [
  {
    name: 'Concepts',
    run: () => ConceptMetadataSchema.array().parse(mockConcepts),
  },
  {
    name: 'Company Details',
    run: () => {
      Object.values(mockCompanyDetails).forEach((details) => {
        CompanyDetailSchema.parse(details);
      });
    },
  },
  {
    name: 'Graph Data',
    run: () => {
      Object.values(mockGraphData).forEach((data) => {
        GraphDataSchema.parse(data);
      });
    },
  },
  {
    name: 'Stock Events',
    run: () => StockEventSchema.array().parse(mockStockEvents),
  },
  {
    name: 'Top Movers',
    run: () => TopMoverSchema.array().parse(mockTopMovers),
  },
  {
    name: 'Sector Bubble Data',
    run: () => SectorBubbleDataSchema.array().parse(getSectorBubbleData()),
  },
  {
    name: 'Sector Performance Stats',
    run: () => SectorPerformanceStatsSchema.parse(getSectorPerformanceStats()),
  },
  {
    name: 'Tree Map Data',
    run: () => TreeMapItemSchema.array().parse(getTreeMapData()),
  },
  {
    name: 'Supply Chain Visual Graph',
    run: () => VisualGraphDataSchema.parse(getSupplyChainData()),
  },
  {
    name: 'Ownership Visual Graph',
    run: () => VisualGraphDataSchema.parse(getOwnershipData()),
  },
  {
    name: 'Cluster Visual Graph',
    run: () => VisualGraphDataSchema.parse(getClusterData()),
  },
  {
    name: 'Interactive Models',
    run: () => InteractiveModelDataSchema.array().parse(INTERACTIVE_MODEL_LIST),
  },
];

let hasErrors = false;

console.log('=== Validating mock data against OpenAPI-derived schemas ===');
for (const validation of validations) {
  try {
    validation.run();
    console.log(`✅ ${validation.name}`);
  } catch (error) {
    hasErrors = true;
    console.error(`❌ ${validation.name} failed`);
    if (error instanceof ZodError) {
      console.error(JSON.stringify(error.errors, null, 2));
    } else {
      console.error(error);
    }
  }
}

if (hasErrors) {
  console.error('\nMock data validation failed');
  process.exit(1);
} else {
  console.log('\nAll mock data matches the OpenAPI schemas ✅');
}


