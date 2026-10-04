# End-Of-Round Owner Sweep

Use when the actual project owner is better placed to distinguish many related
temporary clones, test outputs and helper files. Send to its existing task only;
preserve the user's named work boundary rather than interrupting the active round.

## Bounded Request

Substitute the verified project, current round and exact known roots. The request
is for a full attributable sweep, not just a report of the largest directories:

> There are many <project>-related folders and loose files under D:/Temp. When you
> finish <current round>, clean all of your project's expendable temporary material,
> including older validation clones, worktrees, captures, logs, downloads and
> temporary helpers, not only the current checkout. Preserve required source work
> in the authoritative GitHub repository and verify synchronization before retiring
> its temporary copy. Remove the rest when it is no longer needed through reviewed
> transactional cleanup or the appropriate Git lifecycle. Do not retain a clone
> solely because it has tracked files. Do not upload secrets, signing material,
> sessions or user data to GitHub. Keep genuinely required non-reproducible inputs,
> deliverables and active consumers, giving an exact reason and retention plan for
> each exception. Do not interrupt another task or acquire the Gradle build gate
> for cleanup. Report exact removed roots, deleted bytes, residuals and retained
> paths with reasons; a pending ticket or dry run is not completed cleanup.

The user's shorthand "everything that does not need saving in GitHub should be
removed" expresses a preference against needless retention. It is not an instruction
to publish credentials or delete irreproducible local inputs. Necessary local-only
exceptions need explicit evidence, not blanket repository or recent-timestamp excuses.

## Coordinator Reconciliation

1. Group discovered paths by verified project and task ownership. Search project
   variants and loose helper filenames; a name match is a candidate, not authority.
   Attach known roots without claiming the list is exhaustive.
2. Record one request per owner/project/round in the private ledger. Do not
   dispatch repeats each time the inventory runs. Only request new work if its
   scope or outstanding paths materially differ.
3. Wait for the named round to finish and inspect the owner's cleanup receipt.
   Do not mark a delivered request as a completed sweep or make another build
   wait for broad manifest hashing.
4. Verify removed targets and required retained source/commit synchronization.
   Reconcile every candidate against the owner's removed, retained, shared or
   unresolved list. Independently verified ownerless disposable leftovers can be
   cleaned directly; unresolved ownership is not justification for bulk deletion.
5. Return unjustified retained clones or reproducible litter to the same owner
   as a bounded outstanding cleanup action. Do not force-resume archived tasks
   or create new tasks merely to assign cleanup; investigate directly instead.
