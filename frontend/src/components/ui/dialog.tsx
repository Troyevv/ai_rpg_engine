import {closeButtonSwipe} from '../../gestures/surface';
import {SheetHeight} from '../../gestures/panels';
import {dismissLayer} from '../../gestures/panels';
// shadcn/ui Dialog composition (MIT), backed by Radix focus trap and semantics.
import * as React from "react";
import * as Primitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
export const Dialog = Primitive.Root;
export const DialogTrigger = Primitive.Trigger;
export const DialogClose = Primitive.Close;
export const DialogContent = React.forwardRef<
  React.ElementRef<typeof Primitive.Content>,
  React.ComponentPropsWithoutRef<typeof Primitive.Content>
>(({ className, children, ...props }, ref) => (
  <Primitive.Portal>
    <Primitive.Overlay className="dialog-overlay" />
    <Primitive.Content
      ref={ref}
      className={cn("dialog-content", className)}
      {...props}
    >
      {className?.split(' ').some(name=>['mobile-sheet','time-skip-sheet','current-game-panel'].includes(name))&&<SheetHeight/>}
      {children}
      <Primitive.Close {...closeButtonSwipe()} className="dialog-close" aria-label="Закрыть">
        <X size={20} />
      </Primitive.Close>
    </Primitive.Content>
  </Primitive.Portal>
));
DialogContent.displayName = "DialogContent";
export const DialogHeader = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("dialog-header", className)} {...props} />
);
export const DialogTitle = React.forwardRef<
  React.ElementRef<typeof Primitive.Title>,
  React.ComponentPropsWithoutRef<typeof Primitive.Title>
>(({ className, ...props }, ref) => (
  <Primitive.Title
    {...dismissLayer()}
    ref={ref}
    className={cn("dialog-title", className)}
    {...props}
  />
));
DialogTitle.displayName = "DialogTitle";
export const DialogDescription = React.forwardRef<
  React.ElementRef<typeof Primitive.Description>,
  React.ComponentPropsWithoutRef<typeof Primitive.Description>
>(({ className, ...props }, ref) => (
  <Primitive.Description
    ref={ref}
    className={cn("dialog-description", className)}
    {...props}
  />
));
DialogDescription.displayName = "DialogDescription";
