// Shared chart color tokens - all charts use these so the visual language is consistent
export const C = {
  mint:    "#3DDC97",
  mintDim: "#2A9D6F",
  blue:    "#5B9BD5",
  amber:   "#F2A33C",
  red:     "#E0556F",
  purple:  "#A78BFA",
  teal:    "#22D3EE",
  orange:  "#FB923C",
  text:    "#8B98A9",
  grid:    "#263244",
  surface: "#1A2332",
  raised:  "#222E40",
  border:  "#324158",
};

export const TOOLTIP_STYLE = {
  contentStyle: {
    background: "#1A2332",
    border: "1px solid #324158",
    borderRadius: 6,
    fontSize: 12,
  },
  labelStyle: { color: "#E8EDF2" },
  itemStyle: { color: "#8B98A9" },
};

export const SERVICE_COLORS = {
  EC2: C.mint,
  S3: C.blue,
  RDS: C.amber,
  Lambda: C.purple,
  "Amazon EC2": C.mint,
  "Amazon S3": C.blue,
  "Amazon RDS": C.amber,
  "AWS Lambda": C.purple,
};
