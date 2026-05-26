export interface CatalogField {
  key: string;
  name: string;
  group: string;
  source: string;
  value_type: string;
  default_format: string | null;
  aliases: string[];
}

export interface FieldCatalog {
  id: string;
  label: string;
  fields: CatalogField[];
}

export interface CatalogSummary {
  id: string;
  label: string;
  field_count: number;
}

export interface MatchedField {
  placeholder: string;
  key: string;
  name: string;
  location: string;
  is_image: boolean;
}

export interface UnrecognizedField {
  placeholder: string;
  location: string;
}

export interface UnusedField {
  key: string;
  name: string;
  group: string;
}

export interface ValidateSummary {
  matched_count: number;
  unrecognized_count: number;
  unused_count: number;
  total_catalog_fields: number;
}

export interface ValidateResult {
  matched: MatchedField[];
  unrecognized: UnrecognizedField[];
  unused: UnusedField[];
  summary: ValidateSummary;
}
