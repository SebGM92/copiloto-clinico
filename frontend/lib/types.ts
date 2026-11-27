export type Status = "verified" | "retracted" | "abstained" | "no_evidence" | "blocked";

export type AnswerBlock = { text: string; cites: number[] };

export type Reference = {
  n: number;
  title: string;
  year: number;
  section: string;
  url: string;
  // "caption": rótulo de una tabla ("Tabla Nº 1: …"), que viaja en el fragmento de su tabla
  paragraphs: { page: number; para: number; kind: "text" | "table" | "caption" }[];
  quote: string;
};

export type Final = { status: Status; message: string | null; problems: string[] };
