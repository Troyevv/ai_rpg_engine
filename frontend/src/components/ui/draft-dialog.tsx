import { useState, type ComponentProps } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from './dialog';
import { Button } from './button';
import { tr } from '../../gestures/preferences';

/** Close button, Back and swipe ask the same owner before disposing of a local edit. */
export function DraftDialog({
  dirty,
  onOpenChange,
  children,
  ...props
}: ComponentProps<typeof Dialog> & { dirty: boolean | (() => boolean) }) {
  const [confirm, setConfirm] = useState(false);
  return (
    <Dialog
      {...props}
      onOpenChange={(value) => {
        if (!value && (typeof dirty === 'function' ? dirty() : dirty))
          setConfirm(true);
        else onOpenChange?.(value);
      }}
    >
      {children}
      {confirm && props.open && (
        <Dialog open onOpenChange={setConfirm}>
          <DialogContent data-gesture-confirm="">
            <DialogHeader>
              <DialogTitle>
                {tr('Закрыть без сохранения?', 'Discard this edit?')}
              </DialogTitle>
              <DialogDescription>
                {tr(
                  'В этой форме остались несохранённые изменения.',
                  'This form contains unsaved changes.'
                )}
              </DialogDescription>
            </DialogHeader>
            <div className="actions">
              <Button onClick={() => setConfirm(false)}>
                {tr('Продолжить редактирование', 'Keep editing')}
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setConfirm(false);
                  onOpenChange?.(false);
                }}
              >
                {tr('Закрыть без сохранения', 'Discard and close')}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </Dialog>
  );
}
