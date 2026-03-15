import type { Meta, StoryObj } from "@storybook/react-vite";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "./card";
import { Button } from "./button";

const meta = {
  title: "UI/Card",
  component: Card,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Card container with header, title, description, content, and footer sub-components. " +
          "Used throughout the app for panels, settings sections, and data display.",
      },
    },
  },
  decorators: [
    (Story) => (
      <div style={{ width: 380 }}>
        <Story />
      </div>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof Card>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Full card with all sub-components. */
export const Default: Story = {
  render: () => (
    <Card>
      <CardHeader>
        <CardTitle>Card Title</CardTitle>
        <CardDescription>Card description with supporting text.</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm">This is the card content area. It can contain any content.</p>
      </CardContent>
      <CardFooter>
        <Button variant="outline" size="sm">Cancel</Button>
        <Button size="sm" className="ml-auto">Save</Button>
      </CardFooter>
    </Card>
  ),
};

/** Card with only header and content. */
export const Simple: Story = {
  render: () => (
    <Card>
      <CardHeader>
        <CardTitle>Simple Card</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          A minimal card with just a title and content.
        </p>
      </CardContent>
    </Card>
  ),
};

/** Card with content only (no header). */
export const ContentOnly: Story = {
  render: () => (
    <Card>
      <CardContent className="pt-5">
        <p className="text-sm">Content-only card without a header.</p>
      </CardContent>
    </Card>
  ),
};

/** Multiple cards in a grid layout. */
export const Grid: Story = {
  render: () => (
    <div className="grid grid-cols-2 gap-4" style={{ width: 500 }}>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Sleep Time</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-2xl font-bold">7h 45m</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Efficiency</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-2xl font-bold">93.2%</p>
        </CardContent>
      </Card>
    </div>
  ),
};
