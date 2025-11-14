export interface FormKitDescriptor {
  id: string;
  label: string;
  schemaFile: string;
  schemaPath: string;
  pdfFile: string;
  pdfPath: string;
  description?: string;
}

export interface FormKitManifest {
  generatedAt: string;
  forms: FormKitDescriptor[];
}
