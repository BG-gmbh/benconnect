// NODE_PATH pointing to jsdom and @sinonjs/fake-timers: node --test tests/test_learning_notifications.cjs
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {JSDOM} = require('jsdom');
const FakeTimers = require('@sinonjs/fake-timers');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../flutter_app/docs/js/notifications.js'), 'utf8');

async function setup(t, options = {}) {
  const dom = new JSDOM('<!doctype html><body><header class="site-header"></header></body>', {
    url: 'https://example.test/chat.html', runScripts: 'outside-only', pretendToBeVisual: true,
  });
  const {window} = dom;
  const clock = FakeTimers.withGlobal(window).install({now: 100000, toFake: ['Date', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval']});
  const state = options.state || {pending: true, seen: null, actions: [], fail: false};
  window.fetch = async (url, init) => {
    if (url === '/api/ratings') {
      const data = state.ratings || {open: [], rated: []};
      return {ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(data))};
    }
    if (url.startsWith('/api/ratings/')) {
      if (state.fail) throw new Error('offline');
      const id = url.split('/').pop();
      const values = JSON.parse(init.body);
      const row = state.ratings.open.find(r => r.id === id);
      state.ratings.open = state.ratings.open.filter(r => r.id !== id);
      state.ratings.rated.unshift({...row, ...values});
      return {ok: true, status: 200, json: async () => ({ok: true})};
    }
    const action = init.body && JSON.parse(init.body).action;
    let data;
    if (action) {
      state.actions.push(action);
      if (state.fail && action !== 'seen') throw new Error('offline');
      if (action === 'seen') {
        if (state.seen === null) state.seen = window.Date.now();
        data = {popup_remaining_ms: Math.max(0, state.seen + 30000 - window.Date.now())};
      } else {
        state.pending = false;
        data = {ok: true};
      }
    } else {
      data = {invitations: state.pending ? [{id: 'group1', name: '<img src=x onerror=alert(1)>', subject_label: 'Mathe', invited_by: 'Anna',
        popup_remaining_ms: state.seen === null ? null : Math.max(0, state.seen + 30000 - window.Date.now())}] : []};
    }
    return {ok: true, status: 200, json: async () => data};
  };
  window.eval(source);
  await clock.tickAsync(1);
  t.after(() => {clock.uninstall(); window.close();});
  return {window, clock, state, $: selector => window.document.querySelector(selector)};
}

test('popup lasts 30 seconds and remains actionable under the bell without auto-accepting', async t => {
  const {clock, state, $} = await setup(t);
  assert.ok($('.notification-popups .notification-card'));
  assert.equal($('.notification-popups img'), null, 'names are rendered as text');
  assert.equal($('.notification-count').textContent, '1');
  await clock.tickAsync(29998);
  assert.ok($('.notification-popups .notification-card'));
  await clock.tickAsync(2);
  assert.equal($('.notification-popups .notification-card'), null);
  assert.equal(state.pending, true);
  assert.deepEqual(state.actions, ['seen']);
  $('.notification-bell').click();
  assert.equal($('#notification-inbox').hidden, false);
  $('.notification-list button').click();
  await clock.tickAsync(1);
  assert.deepEqual(state.actions, ['seen', 'accept']);
  assert.equal($('.notification-count').hidden, true);
  assert.match($('.notification-feedback').textContent, /jetzt Mitglied/);
});

test('expired invitations do not pop up again on a later page load', async t => {
  const state = {pending: true, seen: 60000, actions: [], fail: false};
  const {$} = await setup(t, {state});
  assert.equal($('.notification-popups .notification-card'), null);
  $('.notification-bell').click();
  assert.ok($('.notification-list .notification-card'));
  assert.deepEqual(state.actions, []);
});

test('declining dismisses the invitation', async t => {
  const {clock, state, $} = await setup(t);
  $('.notification-popups .btn-secondary').click();
  await clock.tickAsync(1);
  assert.deepEqual(state.actions, ['seen', 'decline']);
  assert.equal($('.notification-popups .notification-card'), null);
  assert.equal($('.notification-count').hidden, true);
});

test('failed confirmation retains invitation and allows retry', async t => {
  const {clock, state, $} = await setup(t);
  state.fail = true;
  $('.notification-popups button').click();
  await clock.tickAsync(1);
  assert.ok($('.notification-popups .notification-error'));
  assert.equal($('.notification-popups button').disabled, false);
  assert.equal(state.pending, true);
  state.fail = false;
  $('.notification-popups button').click();
  await clock.tickAsync(1);
  assert.equal(state.pending, false);
});

test('polling does not replace focused buttons and Escape closes the inbox', async t => {
  const {window, clock, $} = await setup(t);
  const button = $('.notification-popups button');
  button.focus();
  await clock.tickAsync(5000);
  assert.equal(window.document.activeElement, button);
  $('.notification-bell').click();
  window.document.dispatchEvent(new window.KeyboardEvent('keydown', {key: 'Escape'}));
  assert.equal($('#notification-inbox').hidden, true);
  assert.equal(window.document.activeElement, $('.notification-bell'));
});

function ratingState() {
  return {pending: false, seen: null, actions: [], fail: false, ratings: {
    open: [{id: 'task1', subject_label: 'Mathe', appointment: '2026-10-01 10:00', location: 'Bibliothek'}],
    rated: [{id: 'old', subject_label: 'Deutsch', rating: 4, comment: 'Gut'}],
  }};
}

test('open ratings count towards the bell and move to Bewertet after saving', async t => {
  const state = ratingState();
  const {window, clock, $} = await setup(t, {state});
  assert.equal($('.notification-count').textContent, '1');
  assert.equal($('.open-rating-count').textContent, '(1)');
  assert.equal($('.rated-count').textContent, '(1)');
  $('.notification-bell').click();
  const form = $('.open-rating-list form');
  form.querySelector('textarea').value = 'Super';
  form.dispatchEvent(new window.Event('submit', {bubbles: true, cancelable: true}));
  await clock.tickAsync(1);
  assert.equal($('.open-rating-list form'), null);
  assert.equal($('.rated-count').textContent, '(2)');
  assert.equal($('.notification-count').hidden, true);
  assert.match($('.rated-list').textContent, /5\/5 Sterne · Super/);
});

test('rating drafts and focus survive polling and invitation popup expiry', async t => {
  const state = ratingState(); state.pending = true;
  const {window, clock, $} = await setup(t, {state});
  $('.notification-bell').click();
  const comment = $('.open-rating-list textarea');
  comment.value = 'Mein Entwurf'; comment.focus();
  await clock.tickAsync(31000);
  assert.equal($('.open-rating-list textarea'), comment);
  assert.equal(comment.value, 'Mein Entwurf');
  assert.equal(window.document.activeElement, comment);
});

test('low rating requires comment and network failure preserves the rating draft', async t => {
  const state = ratingState();
  const {window, clock, $} = await setup(t, {state});
  const form = $('.open-rating-list form');
  form.querySelector('select').value = '2';
  form.querySelector('select').dispatchEvent(new window.Event('change'));
  assert.equal(form.querySelector('textarea').required, true);
  form.dispatchEvent(new window.Event('submit', {bubbles: true, cancelable: true}));
  assert.match(form.querySelector('[role=alert]').textContent, /Kommentar/);
  assert.equal(state.ratings.open.length, 1);
  form.querySelector('textarea').value = 'Zu laut';
  state.fail = true;
  form.dispatchEvent(new window.Event('submit', {bubbles: true, cancelable: true}));
  await clock.tickAsync(1);
  assert.match(form.querySelector('[role=alert]').textContent, /erneut versuchen/);
  assert.equal(form.querySelector('textarea').value, 'Zu laut');
  assert.equal(form.querySelector('button').disabled, false);
  state.fail = false;
  form.dispatchEvent(new window.Event('submit', {bubbles: true, cancelable: true}));
  await clock.tickAsync(1);
  assert.equal(state.ratings.open.length, 0);
});
