// Java adaptation of AWS CardDemo CBTRN01C.
// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import java.io.BufferedReader;
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public final class DailyTransactionLookup {
    // CVTRA06Y: 1–16 = transaction ID, 263–278 = card number (one-based).
    private static final int TRANSACTION_ID_LENGTH = 16;
    private static final int TRANSACTION_LENGTH = 350;
    private static final int CARD_OFFSET = 262;
    private static final int CARD_LENGTH = 16;
    private static final int ACCOUNT_ID_LENGTH = 11;

    private record CrossReference(String customerId, String accountId) {}

    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("Usage: java DailyTransactionLookup.java <data-directory>");
            System.exit(2);
            return;
        }
        try {
            run(Path.of(args[0]), System.out);
        } catch (IOException | InvalidPathException error) {
            System.err.println(error.getMessage());
            System.err.println("ABENDING PROGRAM (COBOL ABCODE 999)");
            System.exit(1);
        }
    }

    // MAIN-PARA opens all six inputs, including three it only opens and closes.
    @SuppressWarnings("try")
    private static void run(Path directory, PrintStream out) throws IOException {
        out.println("START OF EXECUTION OF PROGRAM CBTRN01C");
        try (var daily = open(directory, "dailytran.txt");
             var customers = open(directory, "custdata.txt");
             var crossReferences = open(directory, "cardxref.txt");
             var cards = open(directory, "carddata.txt");
             var accounts = open(directory, "acctdata.txt");
             var postedTransactions = open(directory, "transact.txt")) {
            var byCard = indexCrossReferences(crossReferences);
            var accountIds = indexAccountIds(accounts);
            processTransactions(daily, byCard, accountIds, out);
        }
        out.println("END OF EXECUTION OF PROGRAM CBTRN01C");
    }

    private static BufferedReader open(Path directory, String filename) throws IOException {
        return Files.newBufferedReader(directory.resolve(filename), StandardCharsets.US_ASCII);
    }

    // CVACT03Y: card 1–16, customer 17–25, account 26–36, then 14 filler bytes.
    private static Map<String, CrossReference> indexCrossReferences(BufferedReader reader)
            throws IOException {
        var byCard = new HashMap<String, CrossReference>();
        for (String line; (line = reader.readLine()) != null; ) {
            int number = byCard.size() + 1;
            checkWidth("cardxref.txt", number, line, 36, 50);
            String card = line.substring(0, CARD_LENGTH);
            var reference = new CrossReference(line.substring(16, 25), line.substring(25, 36));
            if (byCard.putIfAbsent(card, reference) != null) {
                throw new IOException("cardxref.txt line " + number + ": duplicate card " + card);
            }
        }
        return byCard;
    }

    // CVACT01Y: only the 11-byte primary key is used by 3000-READ-ACCOUNT.
    private static Set<String> indexAccountIds(BufferedReader reader) throws IOException {
        var ids = new HashSet<String>();
        for (String line; (line = reader.readLine()) != null; ) {
            int number = ids.size() + 1;
            checkWidth("acctdata.txt", number, line, ACCOUNT_ID_LENGTH, 300);
            String id = line.substring(0, ACCOUNT_ID_LENGTH);
            if (!ids.add(id)) {
                throw new IOException("acctdata.txt line " + number + ": duplicate account " + id);
            }
        }
        return ids;
    }

    private static void processTransactions(BufferedReader daily, Map<String, CrossReference> byCard,
                                            Set<String> accountIds, PrintStream out) throws IOException {
        String current = " ".repeat(TRANSACTION_LENGTH);
        long number = 0;
        for (String line; (line = daily.readLine()) != null; ) {
            checkWidth("dailytran.txt", ++number, line, CARD_OFFSET + CARD_LENGTH, TRANSACTION_LENGTH);
            current = line + " ".repeat(TRANSACTION_LENGTH - line.length());
            out.println(current);
            checkTransaction(current, byCard, accountIds, out);
        }
        // In MAIN-PARA (lines 166–184) the EOF guard covers only DISPLAY.
        // READ INTO leaves the working record in place for this final lookup.
        checkTransaction(current, byCard, accountIds, out);
    }

    private static void checkTransaction(String transaction, Map<String, CrossReference> byCard,
                                         Set<String> accountIds, PrintStream out) {
        String card = transaction.substring(CARD_OFFSET, CARD_OFFSET + CARD_LENGTH);
        CrossReference reference = byCard.get(card);                // 2000-LOOKUP-XREF
        if (reference == null) {
            out.println("INVALID CARD NUMBER FOR XREF");
            out.println("CARD NUMBER " + card + " COULD NOT BE VERIFIED. SKIPPING TRANSACTION ID-"
                    + transaction.substring(0, TRANSACTION_ID_LENGTH));
            return;
        }
        out.println("SUCCESSFUL READ OF XREF");
        out.println("CARD NUMBER: " + card);
        out.println("ACCOUNT ID : " + reference.accountId());
        out.println("CUSTOMER ID: " + reference.customerId());

        if (accountIds.contains(reference.accountId())) {           // 3000-READ-ACCOUNT
            out.println("SUCCESSFUL READ OF ACCOUNT FILE");
        } else {
            out.println("INVALID ACCOUNT NUMBER FOUND");
            out.println("ACCOUNT " + reference.accountId() + " NOT FOUND");
        }
    }

    private static void checkWidth(String file, long lineNumber, String line, int min, int max)
            throws IOException {
        if (line.length() < min || line.length() > max) {
            throw new IOException(file + " line " + lineNumber + ": expected " + min + ".." + max
                    + " ASCII bytes, got " + line.length());
        }
    }
}
