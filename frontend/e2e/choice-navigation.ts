import {expect, type Locator} from '@playwright/test';

export async function openOptions(field: Locator) {
  await field.click();
  const list = field.page().getByRole('listbox');
  await expect(list).toBeVisible();
  return list.getByRole('option');
}

export async function chooseOption(field: Locator, selection: string | {label: string} | {index: number}) {
  const options = await openOptions(field);
  const list = field.page().getByRole('listbox');
  if (typeof selection === 'string') {
    await list.locator('[data-value=' + JSON.stringify(selection) + ']').click();
  } else if ('index' in selection) {
    await options.nth(selection.index).click();
  } else {
    await list.getByRole('option', {name: selection.label, exact: true}).click();
  }
  await expect(list).toHaveCount(0);
}
