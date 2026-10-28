// Infrastructure bootstrap only. Collection validators/indexes belong to Day 3.
const rootUser = encodeURIComponent(process.env.MONGO_INITDB_ROOT_USERNAME);
const rootPassword = encodeURIComponent(process.env.MONGO_INITDB_ROOT_PASSWORD);
let admin;
function waitFor(label, action) {
  for (let attempt = 0; attempt < 180; attempt++) {
    try { if (action()) return; } catch (error) {
      if (attempt === 179) throw error;
    }
    sleep(1000);
  }
  throw new Error(`Timeout waiting for ${label}`);
}
waitFor('authenticated mongo1', () => {
  admin = new Mongo(`mongodb://${rootUser}:${rootPassword}@mongo1:27017/admin?directConnection=true&serverSelectionTimeoutMS=2000`).getDB('admin');
  return admin.runCommand({ping: 1}).ok === 1;
});
try {
  const status = admin.runCommand({replSetGetStatus: 1});
  if (status.ok !== 1) throw status;
} catch (error) {
  if (error.code !== 94 && error.codeName !== 'NotYetInitialized') throw error;
  const result = admin.runCommand({replSetInitiate: {_id: 'oldshop-rs', members: [{_id: 0, host: 'mongo1:27017', priority: 2}]}});
  if (result.ok !== 1) throw new Error(`Replica set initiation failed: ${result.codeName}`);
}
waitFor('mongo1 primary', () => admin.runCommand({hello: 1}).isWritablePrimary === true);
const appDb = admin.getSiblingDB(process.env.MONGO_DB);
if (!appDb.getUser(process.env.MONGO_APP_USER)) {
  appDb.createUser({user: process.env.MONGO_APP_USER, pwd: process.env.MONGO_APP_PASSWORD,
    roles: [{role: 'readWrite', db: process.env.MONGO_DB}]});
}
if (process.env.MONGO_MEMBERS === '3') {
  // MongoDB permits one voting-member addition per reconfiguration.
  for (const [id, host] of [[1, 'mongo2:27017'], [2, 'mongo3:27017']]) {
    waitFor('committed configuration', () => admin.runCommand({replSetGetConfig: 1, commitmentStatus: true}).commitmentStatus === true);
    const current = admin.runCommand({replSetGetConfig: 1}).config;
    if (!current.members.some(member => member.host === host)) {
      current.version += 1;
      current.members.push({_id: id, host, priority: 1, votes: 1});
      const result = admin.runCommand({replSetReconfig: current});
      if (result.ok !== 1) throw new Error(`Reconfiguration failed: ${result.codeName}`);
    }
    waitFor(`${host} secondary`, () => admin.runCommand({replSetGetStatus: 1}).members
      .some(member => member.name === host && member.stateStr === 'SECONDARY'));
  }
}
// A base restart must never shrink an already expanded set.
const members = admin.runCommand({replSetGetStatus: 1}).members;
print(JSON.stringify({replicaSet: 'oldshop-rs', members: members.map(m => ({host: m.name, state: m.stateStr}))}));
