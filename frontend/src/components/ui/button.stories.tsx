import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";
import { Loader2, Plus, Trash2, Download } from "lucide-react";
import { Button } from "./button";

const meta = {
  title: "UI/Button",
  component: Button,
  args: {
    onClick: fn(),
    children: "Button",
  },
  argTypes: {
    variant: {
      control: "select",
      options: ["default", "destructive", "outline", "secondary", "ghost", "link"],
      description: "Visual style variant",
    },
    size: {
      control: "select",
      options: ["default", "sm", "lg", "icon"],
      description: "Button size",
    },
    disabled: {
      control: "boolean",
      description: "Whether the button is disabled",
    },
  },
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

// -- Variants --

export const Default: Story = {
  args: {
    variant: "default",
    children: "Primary Action",
  },
};

export const Destructive: Story = {
  args: {
    variant: "destructive",
    children: "Delete",
  },
};

export const Outline: Story = {
  args: {
    variant: "outline",
    children: "Outline",
  },
};

export const Secondary: Story = {
  args: {
    variant: "secondary",
    children: "Secondary",
  },
};

export const Ghost: Story = {
  args: {
    variant: "ghost",
    children: "Ghost",
  },
};

export const Link: Story = {
  args: {
    variant: "link",
    children: "Link Button",
  },
};

// -- Sizes --

export const Small: Story = {
  args: {
    size: "sm",
    children: "Small",
  },
};

export const Large: Story = {
  args: {
    size: "lg",
    children: "Large",
  },
};

export const Icon: Story = {
  args: {
    size: "icon",
    variant: "outline",
    children: undefined,
  },
  render: (args) => (
    <Button {...args}>
      <Plus className="h-4 w-4" />
    </Button>
  ),
};

// -- States --

export const Disabled: Story = {
  args: {
    disabled: true,
    children: "Disabled",
  },
};

export const Loading: Story = {
  args: {
    disabled: true,
    children: undefined,
  },
  render: (args) => (
    <Button {...args}>
      <Loader2 className="h-4 w-4 animate-spin" />
      Loading...
    </Button>
  ),
};

// -- With Icons --

export const WithLeadingIcon: Story = {
  args: {
    children: undefined,
  },
  render: (args) => (
    <Button {...args}>
      <Download className="h-4 w-4" />
      Export
    </Button>
  ),
};

export const DestructiveWithIcon: Story = {
  args: {
    variant: "destructive",
    children: undefined,
  },
  render: (args) => (
    <Button {...args}>
      <Trash2 className="h-4 w-4" />
      Remove
    </Button>
  ),
};

// -- All Variants Gallery --

export const AllVariants: Story = {
  args: { children: undefined },
  render: () => (
    <div className="flex flex-wrap items-center gap-3">
      <Button variant="default">Default</Button>
      <Button variant="secondary">Secondary</Button>
      <Button variant="destructive">Destructive</Button>
      <Button variant="outline">Outline</Button>
      <Button variant="ghost">Ghost</Button>
      <Button variant="link">Link</Button>
    </div>
  ),
};

export const AllSizes: Story = {
  args: { children: undefined },
  render: () => (
    <div className="flex flex-wrap items-center gap-3">
      <Button size="sm">Small</Button>
      <Button size="default">Default</Button>
      <Button size="lg">Large</Button>
      <Button size="icon">
        <Plus className="h-4 w-4" />
      </Button>
    </div>
  ),
};
